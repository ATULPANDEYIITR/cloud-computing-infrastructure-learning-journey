# Cloud Load Balancers

## Scope

This project models cloud load balancing as a collection of related but distinct mechanisms:

- Application load balancing operates at the HTTP/HTTPS request layer.
- Network load balancing operates at the TCP/TLS connection or flow layer.
- Target groups define the backend population that can receive traffic.
- Health checks determine whether targets are suitable for new traffic.
- Listeners define the protocol and port exposed by the load balancer.
- Target state controls whether a backend can receive new connections.
- Routing policies determine how healthy targets are selected.
- Connection draining allows existing traffic to complete while preventing new traffic from reaching a retiring target.

The implementations deliberately use different engineering perspectives rather than mechanically translating the same program between languages.

| File | Primary perspective | Main responsibility |
|---|---|---|
| Python | Domain simulator | Models target groups, health state, listeners, and routing |
| JavaScript | Event-driven policy model | Models asynchronous health checks and routing behavior |
| C++17 | Routing engine | Implements explicit Layer-4 and Layer-7 selection policies |
| Java 17 | Enterprise domain model | Uses immutable records, services, policies, and explicit state |
| PostgreSQL | Relational operational model | Stores infrastructure state and evaluates operational conditions |

The central relationship is:

`Load Balancer → Listener → Target Group → Health Check → Targets → Routing Decision`

A healthy target is eligible for new traffic. An unhealthy target is removed from normal selection. A draining target remains represented because existing connections may still exist, but it is excluded from new traffic.

---

## Application Load Balancing

Application load balancing operates with application-level information.

For HTTP and HTTPS traffic, the load balancer can reason about information such as:

- host names
- request paths
- HTTP methods
- headers
- cookies
- TLS termination
- application routing rules

A simplified request flow is:

`Client`
`  |`
`  v`
`HTTP/HTTPS Listener`
`  |`
`  v`
`Request-Level Routing`
`  |`
`  v`
`Target Group`
`  |`
`  +----> Healthy Target A`
`  +----> Healthy Target B`
`  +----> Healthy Target C`

The Python implementation uses HTTP routing with a round-robin policy. The JavaScript implementation adds asynchronous health probing. The Java implementation represents routing through a `RoutingPolicy` interface, while PostgreSQL stores the application target group as a relational configuration.

Application load balancing is useful when the routing decision needs to understand the request itself.

A target may therefore receive:

`GET /orders`

while another request may be routed differently because its host or path has different application-level meaning.

---

## Network Load Balancing

Network load balancing operates below the application request layer.

Typical traffic is represented as a network flow:

`Source IP + Source Port + Protocol + Destination Port`

The load balancer does not need to understand an HTTP request body or application route to distribute TCP or TLS traffic.

The project models this distinction using deterministic flow hashing.

For example:

`198.51.100.10:51001/TCP`
`          |`
`          v`
`     Flow Hash`
`          |`
`          v`
`      Target A`

The same flow information produces a stable target selection in the C++ and Java implementations.

This differs from application-level round robin.

| Characteristic | Application load balancing | Network load balancing |
|---|---|---|
| Typical layer | Layer 7 | Layer 4 |
| Typical protocols | HTTP, HTTPS | TCP, TLS |
| Request awareness | Yes | No application request awareness |
| Routing information | Host, path, request properties | Network flow properties |
| Example policy | Round robin | Flow hash |
| Typical concern | Application routing | Connection and flow distribution |

The distinction is architectural. A network load balancer should not be modeled as an HTTP router simply because both distribute traffic.

---

## Target Groups

A target group is the backend population associated with a routing configuration.

A target group in this project contains:

- target identity
- target address
- target port
- protocol
- health-check configuration
- target state
- availability-zone information
- active connection count

The logical relationship is:

`Load Balancer`
`      |`
`      +-- Listener`
`             |`
`             v`
`        Target Group`
`             |`
`      +------+------+`
`      |      |      |`
`      v      v      v`
`   Target  Target  Target`

A target group also establishes an important consistency boundary.

If the group expects port `8080`, a target registered on port `9000` is rejected. This rule is enforced in the Python, JavaScript, C++, Java, and PostgreSQL implementations.

Target groups are therefore not simply lists of IP addresses. They combine backend membership with routing and health semantics.

---

## Listeners

A listener defines the traffic endpoint exposed by the load balancer.

A listener has at least:

- protocol
- port
- target group association

Examples in this project include:

`HTTP:80 → web-targets`

and:

`TCP:443 → tcp-targets`

The listener determines which target group becomes eligible for a request or connection.

The implementations reject routing when no matching listener exists.

This prevents a common configuration failure in which a target group exists but there is no valid frontend entry point connecting client traffic to it.

---

## Health Checks

Health checks determine whether a target is operational enough to receive new traffic.

The project models health-check properties including:

- protocol
- port
- HTTP path where applicable
- check interval
- timeout
- healthy threshold
- unhealthy threshold
- latest result

An HTTP health check may conceptually be:

`GET /health`

A TCP health check can instead test whether a connection can be established on the configured port.

The timing relationship is explicitly validated:

`timeout < interval`

A timeout longer than or equal to the check interval creates an invalid operational model because a new probe could begin before the previous probe has completed.

Health status is separate from target existence.

A target can remain registered while being unhealthy:

`Registered + Unhealthy`

rather than:

`Removed from database`

This distinction is important for diagnosis, recovery, and operational visibility.

---

## Target States

The project uses three target states.

| State | New traffic | Existing connections | Operational meaning |
|---|---:|---:|---|
| `healthy` | Allowed | Allowed | Target is eligible |
| `unhealthy` | Blocked | May continue | Health check indicates failure |
| `draining` | Blocked | May continue | Target is being retired |

The distinction between `unhealthy` and `draining` is intentional.

An unhealthy target represents a failed or unacceptable health condition.

A draining target represents an administrative lifecycle transition. It may still be functioning correctly, but operators do not want new traffic assigned to it.

This is particularly important during deployments, scaling operations, instance replacement, or maintenance.

---

## Connection Draining

Connection draining separates new traffic from existing traffic.

Without draining, removing a target immediately could terminate active work.

With draining:

`New request`
`     |`
`     v`
`Load Balancer`
`     |`
`     X----> Draining Target`
`
`Existing connection`
`     |`
`     v`
`Draining Target`
`     |`
`     v`
`Connection completes`

The target remains visible and its active connection count is retained.

The implementations reject new traffic to a draining target while allowing the operational model to retain its existing connection count.

This is a state-management problem rather than merely a routing algorithm.

---

## Routing Policies

Different load-balancing strategies solve different distribution problems.

### Round Robin

Round robin selects targets sequentially:

`A → B → C → A → B → C`

The Python, JavaScript, and Java application-oriented implementations use this policy.

Its main advantage is simplicity and predictable distribution when targets have similar capacity.

Its limitation is that it does not directly account for current connection counts or request cost.

### Flow Hash

Flow hashing derives a deterministic selection from connection attributes.

A simplified flow key is:

`source address + source port + protocol + destination port`

The C++ and Java implementations use deterministic hashing for network traffic.

The same flow can therefore repeatedly map to the same target under stable conditions.

This differs from round robin because the selection is based on flow identity rather than request arrival order.

### Least Connections

The PostgreSQL model recognizes `least_connections` as a valid target-group algorithm even though the executable routing simulations focus on round robin and flow hashing.

Least-connections routing can be useful when connections have significantly different lifetimes or workloads.

The database model keeps the algorithm as explicit configuration rather than silently assuming that every target group behaves identically.

---

## Python Implementation

The Python implementation is a self-contained domain simulator.

Important domain objects are represented by dataclasses:

- `HealthCheck`
- `Target`
- `TargetGroup`
- `Request`
- `Listener`
- `LoadBalancer`

Enums make operational states explicit.

`LoadBalancerType` distinguishes application and network behavior.

`TargetState` distinguishes healthy, unhealthy, and draining targets.

The routing service performs the following sequence:

`Request`
`  ↓`
`Listener lookup`
`  ↓`
`Target group lookup`
`  ↓`
`Healthy-target filtering`
`  ↓`
`Routing policy`
`  ↓`
`Connection accounting`

Validation occurs before objects enter the active model.

The script also demonstrates:

- target failure
- target draining
- connection counting
- no-healthy-target failure
- listener validation
- port validation
- HTTP health-check validation
- executable assertions

The implementation uses only the Python standard library.

---

## JavaScript Implementation

The JavaScript implementation uses an event-driven style suitable for Node.js.

`Map` objects represent target groups and targets efficiently.

The asynchronous `runHealthCheck` method accepts an injected probe function. This keeps the model dependency-free while preserving the structure needed for a real network probe.

The flow is:

`runHealthCheck()`
`      ↓`
`await probe()`
`      ↓`
`PASS / FAIL`
`      ↓`
`Target state update`

This is different from the Python implementation because the JavaScript version explicitly models asynchronous operations.

The network routing policy uses a deterministic hash derived from connection information.

The application routing policy uses round robin.

Error classes distinguish configuration failures from generic runtime failures.

The implementation also checks that unhealthy or draining targets cannot receive new traffic.

---

## C++17 Implementation

The C++ program models a routing engine with explicit ownership and policy boundaries.

Important components include:

- `HealthCheck`
- `Target`
- `TargetGroup`
- `Request`
- `Listener`
- `GovernanceEngine`

The `GovernanceEngine` selects the appropriate routing strategy according to load-balancer type.

Application routing uses a round-robin index.

Network routing uses a deterministic flow hash.

C++17 STL containers provide efficient storage for target groups, targets, listeners, and routing state.

The implementation uses exceptions for invalid configuration and impossible state transitions.

The use of `std::optional` for HTTP health-check paths expresses an important protocol distinction:

- HTTP/HTTPS health checks require a path.
- TCP/TLS checks do not require an HTTP path.

The implementation also models connection closing separately from routing. This prevents the active-connection count from becoming an implicit side effect with no lifecycle operation.

---

## Java 17 Implementation

The Java implementation uses an enterprise-oriented domain model.

Java records represent immutable value objects:

- `HealthCheckPolicy`
- `Listener`
- `ClientRequest`
- `RouteResult`

Mutable operational entities such as `Target` maintain state transitions.

The `RoutingPolicy` interface separates policy from orchestration.

Two implementations are provided:

- `RoundRobinPolicy`
- `FlowHashPolicy`

The `HealthService` owns health-result application.

The `MergeLikeRoutingService` coordinates:

`Listener`
`   ↓`
`Target Group`
`   ↓`
`Health Filter`
`   ↓`
`Routing Policy`
`   ↓`
`Target`
`   ↓`
`Connection State`

This structure prevents the main service from embedding every routing algorithm directly.

Custom exceptions distinguish:

- configuration errors
- routing errors

Java streams are used for healthy-target filtering, while explicit domain methods enforce state transitions such as draining and connection closing.

---

## PostgreSQL Model

The PostgreSQL implementation treats load-balancer configuration and operational state as relational data.

The primary relationships are:

`repositories`
`    |`
`    +-- branches`
`    +-- target_groups`
`          |`
`          +-- health_checks`
`          +-- targets`
`    +-- listeners`

Targets belong to target groups through a foreign key.

Health checks belong one-to-one with target groups.

Listeners associate a protocol and port with a target-group name.

### Constraints

The schema uses database-level constraints for rules that should not depend on application code.

Examples include:

- valid TCP/UDP-style port ranges
- non-negative active connections
- positive health-check thresholds
- timeout shorter than interval
- non-empty target names
- valid target states
- valid routing algorithms
- unique target names within target groups
- unique listeners within a repository

A trigger verifies that the target port matches the target-group port.

Another trigger protects HTTP and HTTPS health checks from being created without a path.

---

## Health Reporting

The `target_health_report` view aggregates target state.

It exposes:

- total targets
- healthy targets
- unhealthy targets
- draining targets
- protocol
- target-group port

This supports operational questions such as:

`How many healthy backends remain?`

and:

`Which target groups are losing capacity?`

The aggregation is performed in PostgreSQL rather than reconstructed in application code.

---

## Routing Distribution

The `routing_events` table records representative routing activity.

It stores:

- selected target
- source address
- protocol
- source port
- selection timestamp

The `request_distribution` view aggregates these events.

This separates configuration from observed activity.

Configuration answers:

`What should happen?`

Routing events answer:

`What happened?`

The distinction is useful for operational analysis.

---

## Merge Eligibility Model

The database also demonstrates how multiple operational conditions can be evaluated together.

The `evaluate_merge_eligibility` function evaluates:

- Pull Request state
- draft status
- mergeability
- healthy target count
- required health checks
- required approvals
- unresolved review comments
- application protocol requirements

The function returns both a Boolean eligibility result and a human-readable reason.

For example:

`Insufficient healthy targets`

is different from:

`Required approvals are missing`

and from:

`One or more required health checks are failing`.

This is important because a Boolean result alone does not explain an operational failure.

---

## Transactions

The PostgreSQL script uses a transaction when changing an unhealthy target into a draining state.

The transaction boundary makes the state transition atomic from the database perspective.

The important operational sequence is:

`BEGIN`
`  ↓`
`Change target lifecycle state`
`  ↓`
`COMMIT`

If an error occurs before the commit, the state change can be rolled back.

This becomes important when a production workflow updates several related records at once.

---

## Failure Conditions

The implementations intentionally reject invalid or unsafe states.

Examples include:

- no listener for a requested protocol and port
- no healthy targets
- target port differs from target-group port
- invalid listener configuration
- HTTP health check without a path
- health-check timeout not shorter than its interval
- duplicate target identifiers
- duplicate target groups
- unknown target identifiers
- closing a connection that is not active
- routing with an incompatible load-balancer type
- attempting to send new traffic to a draining target

These are domain failures rather than syntax failures.

---

## Security Considerations

Load balancing is part of the network security boundary, but a load balancer does not automatically make an application secure.

Relevant controls include:

- TLS for encrypted client connections
- restricted listener exposure
- controlled target registration
- health-check endpoints that do not expose sensitive information
- private backend addresses where appropriate
- least-privilege access to load-balancer configuration
- logging of routing and configuration changes
- protection against accidental direct backend exposure
- controlled target lifecycle transitions

Health endpoints should expose enough information to determine service readiness without revealing credentials, secrets, internal topology, or sensitive application data.

Source addresses should also be treated as untrusted input when they originate from client-controlled traffic.

---

## Performance Considerations

The routing simulations primarily use in-memory collections.

For a target group with `n` targets:

- round-robin selection is effectively `O(1)` after healthy-target collection
- flow-hash selection is effectively `O(k)` for a flow key of length `k`
- rebuilding the healthy-target list is `O(n)`

The PostgreSQL health report performs grouped aggregation over target records.

Indexes are therefore placed on fields used for:

- target-group membership and state
- Pull Request status checks
- review state
- routing-event history

Indexes are not added indiscriminately because every index creates storage and write-maintenance cost.

---

## Availability-Zone Distribution

Targets include availability-zone metadata.

A practical deployment should avoid placing all backend capacity in one failure domain.

The model therefore supports:

`Target Group`
`   |`
`   +-- zone-a`
`   |     +-- target`
`   |     +-- target`
`   |`
`   +-- zone-b`
`   |     +-- target`
`   |`
`   +-- zone-c`
`         +-- target`

Health status should be considered together with zone distribution.

Three registered targets do not necessarily represent three independent failure domains if all three reside on the same underlying infrastructure.

---

## Operational Workflow

A typical lifecycle represented by the project is:

`1. Create load balancer`
`        ↓`
`2. Configure listener`
`        ↓`
`3. Create target group`
`        ↓`
`4. Register targets`
`        ↓`
`5. Configure health checks`
`        ↓`
`6. Evaluate target health`
`        ↓`
`7. Route only to eligible targets`
`        ↓`
`8. Drain targets during replacement`
`        ↓`
`9. Remove targets after active connections finish`

Each stage has different responsibilities.

Listener configuration does not replace health checking.

Health checking does not determine the routing algorithm.

Routing policy does not replace target lifecycle management.

Connection draining does not mean the target is healthy.

Keeping these responsibilities separate makes the model easier to validate and operate.

---

## Important Distinctions

### Load Balancer vs Target Group

The load balancer is the traffic-distribution component.

The target group is the backend membership and health boundary.

### Listener vs Target

A listener accepts traffic on a frontend protocol and port.

A target is a backend destination.

### Health Check vs Routing Policy

A health check determines eligibility.

A routing policy chooses among eligible targets.

### Unhealthy vs Draining

Unhealthy is a health condition.

Draining is a lifecycle condition.

Both block new traffic in this model, but they have different operational meanings.

### Application vs Network Load Balancing

Application load balancing can reason about application requests.

Network load balancing works with network flows and does not require application-level request interpretation.

---

## Practical Failure Scenario

Consider three application targets:

`web-a = healthy`
`web-b = healthy`
`web-c = unhealthy`

The target group has two available targets.

If `web-b` later fails its health check:

`web-a = healthy`
`web-b = unhealthy`
`web-c = unhealthy`

The system still has one healthy target.

If the minimum healthy capacity is two, the operational state should be considered degraded even though traffic can technically still be routed.

If `web-a` is then placed into draining state:

`web-a = draining`
`web-b = unhealthy`
`web-c = unhealthy`

No target can receive new traffic.

This illustrates why simple target existence is not enough to determine service availability.

---

## Design Decisions

The implementations intentionally do not attempt to reproduce every feature of a commercial cloud provider.

The focus is on the underlying mechanisms that make cloud load balancing understandable:

- frontend listeners
- backend target groups
- health-based eligibility
- routing policies
- state transitions
- connection accounting
- database constraints
- operational reporting

The model does not depend on provider-specific APIs, proprietary SDKs, or external services.

This keeps the behavior deterministic and makes the underlying architecture visible.

---

## Educational Structure

The project progresses from domain representation to operational policy.

Python emphasizes a compact executable model.

JavaScript emphasizes asynchronous behavior and event-driven health evaluation.

C++17 emphasizes a high-performance routing engine and explicit flow hashing.

Java 17 emphasizes enterprise domain modeling, policy interfaces, immutable records, and service boundaries.

PostgreSQL emphasizes durable state, relational integrity, constraints, triggers, reporting views, and transactional operations.

The five perspectives represent the same cloud infrastructure domain without requiring the implementations to be identical.

The central engineering lesson is that cloud load balancing is not one algorithm.

It is a coordinated system consisting of:

`Traffic Entry`
`     ↓`
`Protocol / Listener`
`     ↓`
`Routing Policy`
`     ↓`
`Target Eligibility`
`     ↓`
`Target Selection`
`     ↓`
`Connection Lifecycle`
`     ↓`
`Operational State`

Each stage has a distinct responsibility, and production reliability depends on keeping those responsibilities consistent.
