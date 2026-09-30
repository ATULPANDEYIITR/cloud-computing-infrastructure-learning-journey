# Load Balancing Fundamentals

## Scope

Load balancing distributes client traffic across multiple backend servers so that a service can use available capacity more effectively and continue operating when individual backends fail.

This repository focuses on four closely related but distinct areas:

- **Layer 4 load balancing**, where routing decisions are based primarily on transport information such as TCP connections.
- **Layer 7 load balancing**, where the load balancer understands application protocols such as HTTP and can route according to paths, methods, headers, or other application metadata.
- **Traffic distribution**, which determines how eligible backends receive new connections or requests.
- **Health checks and sticky sessions**, which determine whether a backend should receive traffic and whether a particular client session should remain associated with one backend.

The implementations deliberately model these mechanisms rather than pretending that a small standalone program is a complete production network proxy.

## Core Model

A typical load-balanced service contains clients, a load balancer, and several backend servers.

A simplified request path is:

Client → Load Balancer → Backend Pool

The load balancer normally performs several logically separate decisions:

`incoming traffic → protocol classification → backend eligibility → routing policy → backend selection → connection/request processing → response`

Backend eligibility is not the same thing as traffic distribution. A server can have a configured weight but still be excluded because it is unhealthy, draining, or at capacity.

That distinction is central to the implementations.

## Layer 4 Load Balancing

Layer 4 refers to the transport layer. For TCP services, the load balancer can make decisions without understanding the application protocol carried inside the connection.

A Layer 4 load balancer can use information such as:

- source IP address
- destination IP address
- source port
- destination port
- TCP connection state
- transport protocol

A TCP connection can therefore be routed to `app-01`, for example, without inspecting an HTTP request such as `GET /api/orders`.

This is useful for protocols that are not HTTP and for workloads where application-level inspection is unnecessary.

Layer 4 routing also has an important limitation: the load balancer cannot naturally make an HTTP path decision if it deliberately treats the payload as opaque transport traffic.

The Python implementation represents this with `Protocol.TCP`. Its `LoadBalancer` selects a backend without using an HTTP path.

The C++ case study uses the same distinction. A `Request` marked as `Protocol::TCP` bypasses the `HttpRouter`.

## Layer 7 Load Balancing

Layer 7 load balancing operates with application-level information.

For HTTP, the load balancer can understand:

- HTTP method
- URL path
- host
- headers
- cookies
- application-specific routing metadata

This enables rules such as:

`/api/` → API backend pool

`/static/` → static-content backend pool

`GET /checkout` → application service

Layer 7 routing therefore provides more routing precision than transport-only balancing, but it also requires the load balancer to understand and process application traffic.

The Python program uses `path_routes` to demonstrate direct path-based routing.

The JavaScript program uses `HttpRouter`, where rules contain a method, path prefix, and backend identifier. This implementation demonstrates why HTTP-aware routing is fundamentally different from simply selecting the next TCP server.

The C++ program uses `HttpRouter::match()` and `RouteRule`. A route is selected only when both the HTTP method and path prefix match the request.

## Layer 4 and Layer 7 Relationship

Layer 4 and Layer 7 are not competing names for exactly the same operation.

A Layer 4 decision might effectively be:

`TCP connection from client X → backend B`

A Layer 7 decision can be:

`GET /api/orders → API backend`

The latter requires inspection of application information that does not exist at the transport-routing level.

A practical architecture can use Layer 4 balancing for one service and Layer 7 balancing for another. A system can also have different layers of traffic management in front of the same application.

## Traffic Distribution

After unhealthy and unavailable backends are excluded, a load balancer needs a selection policy.

### Round Robin

Round robin rotates through eligible servers.

For three equally capable servers, a simplified sequence is:

`A → B → C → A → B → C`

The Python `RoundRobinBalancer`, JavaScript `RoundRobin`, and C++ `TrafficSelector::roundRobin()` implement this policy.

Round robin is simple and predictable, but it does not know whether one backend is already processing significantly more expensive or long-lived work.

### Weighted Distribution

Weighted routing gives backends different relative shares.

For weights:

`A = 3, B = 2, C = 1`

the scheduler can construct an effective sequence containing three references to A, two to B, and one to C.

The Python and C++ implementations use this approach directly, while the JavaScript implementation creates a weighted pool.

Weights are useful when servers have different capacities. They are not a guarantee that response latency, CPU utilization, memory utilization, or actual work will be proportional to the configured values.

### Least Connections

Least-connections routing considers current connection counts.

If the current state is:

| Backend | Active connections |
|---|---:|
| A | 8 |
| B | 2 |
| C | 5 |

a new connection can be directed to B.

This is particularly relevant when connections have significantly different lifetimes. It can react to current load in a way that simple round robin cannot.

The C++ case study explicitly creates an uneven active-connection state before making a routing decision.

### IP Hash

IP hashing maps a client IP to a backend deterministically.

This can provide a form of affinity without maintaining a separate session table. A simplified model is:

`hash(client IP) % number of eligible backends`

A significant operational issue is backend membership. If the backend set changes, a basic modulo-based hash can remap many clients. Production systems that require stable hashing often use more sophisticated consistent-hashing techniques.

The JavaScript implementation uses an explicit FNV-style integer hashing routine to demonstrate deterministic client selection.

## Backend Eligibility

Traffic distribution should operate on an eligible backend set rather than blindly selecting from every configured server.

The implementations consider conditions such as:

- backend health
- backend state
- maximum connection capacity
- configured weight

The Python `BackendServer.can_accept()` method centralizes this rule.

The C++ `Backend::canAccept()` performs the same conceptual operation.

This separation is important because an algorithm such as round robin should not repeatedly choose a server that has already been declared unavailable.

## Health Checks

A health check tests whether a backend should continue receiving traffic.

Common approaches include:

- TCP connection checks
- HTTP endpoint checks
- application-specific readiness checks
- dependency-aware readiness checks

A health check should answer a carefully defined question. A TCP port accepting connections does not necessarily mean that the application is able to serve requests correctly.

The JavaScript implementation represents this distinction with:

`health.endpointAvailable`

and:

`applicationHealthy`

The backend can therefore accept a connection while its application still reports a failure.

### Failure Thresholds

Immediately removing a backend after one failed probe can cause false positives from transient network problems.

The JavaScript `HealthMonitor` uses consecutive failure and recovery thresholds. The C++ `HealthChecker` uses the same concept.

For example:

`failure threshold = 2`

means two consecutive failed checks are required before the backend becomes unhealthy.

A recovery threshold can require multiple successful checks before the backend is returned to normal service.

This creates hysteresis between failure and recovery and reduces rapid state oscillation.

### Health Check Interval and Timeout

A production health-check design must balance detection speed and system overhead.

A very short interval can detect failures quickly but generates more probing traffic.

A very long interval reduces monitoring overhead but can leave failed servers in the traffic pool for longer.

A timeout is equally important. A backend that never responds should not cause health-check workers to wait indefinitely.

The Python `HealthChecker` includes a timeout policy, while the JavaScript implementation models asynchronous probe latency with a Promise.

## Health and Application Correctness

A backend has at least two distinct operational properties:

`Can I establish communication with it?`

and:

`Can its application successfully process requests?`

These are not equivalent.

The Python failure simulation marks a backend's health endpoint as failed and separately supports an application failure state.

The JavaScript and C++ programs explicitly distinguish routing success from application success.

This distinction is important when designing monitoring. A load balancer that only tests whether a process accepts TCP connections may continue sending traffic to an application that is technically reachable but functionally broken.

## Sticky Sessions

Sticky sessions, also called session affinity, associate a session with a particular backend.

A simplified mapping is:

`session-42 → app-02`

Subsequent requests for `session-42` are sent to `app-02` while that backend remains eligible.

This can be useful when application state is stored locally on a backend rather than in a shared session store.

The Python implementation stores mappings in `StickySessionBalancer.session_map`.

The JavaScript implementation uses a `Map`.

The C++ implementation uses `std::unordered_map`.

### Sticky Session Failure

Affinity must not override backend health.

If the backend associated with `session-42` becomes unhealthy, continuing to route the session there would defeat failure isolation.

The implementations therefore invalidate or ignore a stale session mapping when its backend becomes unavailable.

A new eligible backend can then receive the session.

The practical consequence is that applications relying on in-memory session state must be prepared for the possibility that a user moves to another backend after failure.

## Sticky Sessions and Load Distribution

Sticky sessions can conflict with even traffic distribution.

Suppose one backend receives many sessions while another receives relatively few. A round-robin algorithm might have distributed new requests evenly, but affinity can keep existing users attached to their original servers.

This is one reason shared application state is often preferable when practical.

With externalized state, any healthy backend can process the next request without depending on a particular server's local memory.

The choice is architectural rather than merely a load-balancer configuration option.

## Connection Draining

A backend may need to stop receiving new traffic without immediately terminating existing work.

This state is represented as `Draining` in all three implementations.

A draining backend should generally:

- stop receiving new connections
- allow existing connections to finish
- remain observable during the transition
- eventually become removable from the service pool

This is useful during deployments, maintenance, and controlled server replacement.

The Python `drain_backend()` method changes the backend state and removes stale sticky mappings.

The JavaScript implementation exposes `drainBackend()`.

The C++ case study uses `LoadBalancer::drain()`.

## Capacity and Overload

Health alone does not describe capacity.

A server may be healthy but unable to accept additional work because it has reached its connection limit.

The implementations therefore distinguish:

`healthy`

from:

`eligible to accept another connection`

The Python `BackendServer` has `max_connections` and `active_connections`.

The JavaScript `Backend` performs the same capacity check.

The C++ `Backend::canAccept()` combines health state and connection capacity.

A production system may also consider CPU, memory, queue depth, concurrency limits, rate limits, and application-specific overload signals.

## Request Lifecycle

A simplified lifecycle represented by the implementations is:

`request arrives`

→ identify transport/application protocol

→ determine whether Layer 7 rules apply

→ construct the eligible backend set

→ apply the selected distribution policy

→ establish or allocate backend work

→ process the application request

→ record success or failure

→ release the connection or request slot

Health checks operate alongside this lifecycle rather than being part of the individual request itself.

They continuously influence which backends enter the eligible pool.

## Python Implementation

The Python program provides the broadest simulation of the fundamentals.

`BackendServer` represents a service instance with:

- identity
- network address
- port
- weight
- health state
- connection capacity
- active connections
- request counters
- health counters

The routing implementations are deliberately separate classes:

- `RoundRobinBalancer`
- `WeightedRoundRobinBalancer`
- `LeastConnectionsBalancer`
- `IPHashBalancer`
- `StickySessionBalancer`

This separation makes the traffic-selection mechanism independent from the `LoadBalancer` controller.

The Python program also demonstrates HTTP path routing through `path_routes`, health transitions, connection capacity, sticky-session recovery, backend draining, and application failure.

The program can be executed directly with Python 3:

`python load_balancer.py`

No external package is required.

## JavaScript Implementation

The JavaScript implementation takes an event-driven approach appropriate for Node.js.

`EventEmitter` is used by `HealthMonitor` so backend failure and recovery become explicit events rather than merely return values.

This is useful because production infrastructure often reacts to state transitions by updating routing tables, invalidating affinity information, emitting metrics, or generating operational events.

`HealthMonitor.check()` is asynchronous and uses a Promise to model probe latency. This demonstrates a JavaScript-specific concern that differs from the synchronous Python simulation.

The JavaScript `HttpRouter` provides method-and-prefix matching, while `StickySessions` uses `Map` for session-to-backend state.

The implementation can be executed with:

`node load_balancer.js`

No npm dependency is required.

## C++ Case Study

The C++ program models a repository-independent service with a stronger systems-programming perspective.

The main entities are:

- `Backend`
- `Request`
- `RouteRule`
- `HealthChecker`
- `TrafficSelector`
- `StickySessionTable`
- `HttpRouter`
- `LoadBalancer`

`Backend` owns connection and health state.

`TrafficSelector` implements several distribution policies.

`HttpRouter` handles Layer 7 matching.

`StickySessionTable` maintains application-session affinity.

`HealthChecker` controls health-state transitions.

`LoadBalancer` coordinates these components and records routing and application failures.

The program also demonstrates connection draining, health recovery thresholds, weighted routing, least-connections routing, application failures, and transport-versus-application distinctions.

The program is compatible with C++17 or later. A typical compilation command is:

`g++ -std=c++17 -O2 load_balancer.cpp -o load_balancer`

The resulting executable can be run directly.

## Failure Handling

A load balancer must distinguish several failure classes.

### Backend failure

A backend can fail its health check and be removed from the eligible pool.

### Capacity exhaustion

A backend can be healthy but unable to accept additional connections.

### Application failure

A backend can accept network connections while its application returns errors.

### Affinity failure

A sticky-session mapping can point to a backend that is no longer eligible.

### Draining state

A backend can intentionally stop accepting new traffic while existing work completes.

These conditions require different responses. Treating all of them as the same failure can lead to incorrect routing and poor recovery behavior.

## Common Design Errors

### Treating health as a binary concept

A TCP port being reachable is not proof that the application is ready. Health endpoints should represent an intentionally defined readiness condition.

### Ignoring backend capacity

A healthy server that is saturated can still degrade service. Backend eligibility should consider capacity where appropriate.

### Using sticky sessions without considering failure

Affinity can preserve local state but makes failover more complicated. Session state that must survive backend loss should not depend exclusively on local memory.

### Assuming weighted routing guarantees equal performance

Weights describe routing preference, not actual response-time guarantees. Different requests can have radically different computational costs.

### Using IP hashing as universal session management

Client IP can change because of mobile networks, proxies, NAT, or network topology. IP-based affinity is not equivalent to application-session identity.

### Making health checks too shallow

A probe that checks only process availability can miss dependency failures that prevent the application from serving useful responses.

### Making health checks too aggressive

Very short intervals and low failure thresholds can cause healthy servers to flap between available and unavailable states because of transient problems.

## Performance Considerations

Round robin generally has low selection overhead because it maintains a cursor over eligible servers.

Weighted selection implemented through an expanded list is easy to understand but can consume additional memory when weights become very large. A production implementation may use a more efficient weighted scheduling algorithm.

Least-connections requires observing backend state and comparing candidates. Its decision quality depends on the accuracy and freshness of connection counts.

Hash-based routing has efficient lookup characteristics but backend membership changes can affect affinity.

Layer 7 inspection requires parsing application protocol information, which introduces processing work that a transparent Layer 4 decision does not require.

Health checks consume network and backend resources. Probe frequency should therefore be selected with service size and failure-detection requirements in mind.

## Security Considerations

A load balancer becomes part of the service's trust boundary.

HTTP routing rules should validate paths and other routing inputs rather than assuming that all incoming values are safe.

Header-based routing must account for which headers can be trusted from clients and which are inserted or sanitized by trusted infrastructure.

Client IP handling requires care when proxies or forwarding headers are involved. Blindly trusting an attacker-controlled forwarding header can result in incorrect client identity and security decisions.

Health endpoints should avoid exposing sensitive diagnostic information. A health endpoint should communicate enough operational state for routing without unnecessarily exposing internal details.

Administrative operations such as draining a backend or modifying routing rules require authentication and authorization in real systems.

## Operational Metrics

Useful load-balancer measurements include:

- requests received
- routing failures
- backend selection counts
- backend health transitions
- active connections
- connection rejection counts
- application error rates
- health-check latency
- backend response latency
- sticky-session distribution
- connection-draining duration

A single aggregate availability number is not enough to diagnose an imbalanced backend pool.

For example, if all servers are healthy but one server receives most requests because of sticky sessions, health monitoring alone may not reveal the distribution problem.

## Practical Relationship Between the Mechanisms

The four main areas form a chain of responsibilities.

**Layer 4** determines how transport connections can be distributed without requiring application awareness.

**Layer 7** adds application-level routing decisions such as HTTP path and method matching.

**Traffic distribution** determines which eligible backend receives traffic when there is no more specific routing rule.

**Health checks** determine whether a backend belongs in the eligible set.

**Sticky sessions** modify normal distribution by preserving an association between a client session and a backend, while still needing to respect backend health and capacity.

A useful conceptual model is:

`Layer 4 or Layer 7 classification → health/capacity eligibility → routing policy → optional session affinity → backend`

The implementations keep these responsibilities separate so that changing a routing algorithm does not require rewriting health-check logic, and changing an HTTP route does not require changing the backend state model.

## Limitations of the Simulations

These programs do not implement real packet forwarding, TLS termination, TCP retransmission handling, HTTP/2, HTTP/3, WebSockets, connection pooling, kernel-level networking, distributed health-check coordination, distributed session storage, or production-grade consistent hashing.

The health-check and connection behavior is simulated locally.

The purpose of the implementations is to make the routing decisions, backend state transitions, traffic policies, and failure relationships executable and observable without requiring a real multi-server deployment.
