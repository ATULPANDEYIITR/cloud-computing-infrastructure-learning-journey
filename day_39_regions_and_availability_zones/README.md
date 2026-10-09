# Regions and Availability Zones: Geographic Redundancy and Multi-Zone Architecture

## Scope

Regional infrastructure design determines where applications, data, network services, and recovery capabilities operate. Regions establish broad geographic and administrative boundaries. Availability zones provide separate infrastructure locations within a region. Geographic redundancy extends resilience across regions, while multi-zone architecture distributes resources across zones to reduce exposure to localized failures.

These mechanisms address different failure scenarios. Multiple zones within one region can withstand certain localized infrastructure outages without necessarily protecting against regional disruptions. Multiple regions can extend the recovery boundary, but introduce additional requirements for data replication, routing, consistency, operational coordination, and regulatory compliance.

The five executable implementations model topology, workload placement, capacity, zone failures, service availability, and recovery-related decisions using different programming and database approaches.

## Regional and zone topology

A region is a geographic infrastructure grouping with a defined service boundary. It can influence latency, data residency, pricing, service availability, and disaster recovery design. A region should not be treated as a guarantee that every component within it is independent of every other component.

An availability zone is an infrastructure location within a region. Depending on the provider, a zone may represent one or more data centers with independent or partially independent power, cooling, networking, and other infrastructure. Zone identifiers and physical arrangements are provider-specific.

The modeled hierarchy is:

    Geographic deployment
        Region
            Availability Zone
                Compute and application replicas
                Storage replicas
                Network paths
                Infrastructure dependencies

The Python, JavaScript, C++, and Java programs represent regions as containers of zones. Each zone has a state, capacity, latency estimate, and modeled failure domains. The SQL implementation stores these relationships with primary keys, foreign keys, and a many-to-many association between zones and failure domains.

A zone identifier alone does not prove physical independence. A realistic deployment must use provider documentation and observed architecture to establish which failure boundaries are genuinely independent.

## Failure domains and isolation

A failure domain is the set of resources that may fail together because they depend on a shared component or failure event.

Examples include:

- A power domain containing equipment dependent on a shared electrical supply.
- A network domain containing workloads dependent on a shared routing path.
- A cooling domain containing equipment exposed to a shared cooling failure.
- A control-plane domain containing services dependent on a shared management system.
- A regional domain containing services exposed to a broad regional outage.

A placement policy can avoid known shared domains when distributing replicas. The implementations represent these dependencies with sets, relational associations, or domain objects. Their placement algorithms reject zones with overlapping modeled failure domains.

This check is only as accurate as the topology information supplied to the model. Two zones with different labels can still share upstream networking, identity services, DNS, deployment systems, or management dependencies.

Failure-domain diversity should therefore be evaluated at multiple layers rather than inferred from zone count alone.

## Multi-zone architecture

Multi-zone architecture distributes application instances across separate zones within a region. It is useful when a service must continue operating after a localized infrastructure outage.

The sample workload named `checkout` or `checkout-service` uses three replicas and requires at least two healthy replicas. Losing one zone leaves two healthy replicas, satisfying the configured availability condition.

Replica count and minimum healthy count express different requirements:

- Desired replicas determine the intended deployment size.
- Minimum healthy replicas determine the threshold below which the service is considered unavailable.
- Available capacity determines whether replacement or additional replicas can be scheduled.
- Placement constraints determine whether the replicas are sufficiently separated.

A replica count of three does not automatically imply fault tolerance. All three replicas could be placed in one zone, depend on the same database, or share a single network path. Placement and dependency analysis are essential.

The implementations focus on placement and health evaluation. They do not claim to deploy actual infrastructure or automatically restore application data.

## Geographic redundancy

Geographic redundancy distributes application capabilities across multiple regions. It addresses failures that extend beyond one availability zone and may include regional service disruptions.

A multi-region architecture needs an explicit traffic-routing and data-management design. Application instances alone are insufficient when all instances depend on a database or other critical service located in only one region.

Common deployment patterns include:

| Pattern | Operational characteristics | Main trade-off |
|---|---|---|
| Active-passive | A primary region serves traffic while a standby region maintains recovery capability. | Lower normal operating complexity, but failover may require promotion and traffic changes. |
| Active-active | Multiple regions serve traffic concurrently. | Higher capacity utilization and geographic reach, but more complex data consistency and conflict handling. |
| Read-local, write-primary | Reads may be served regionally while writes go to a designated primary. | Reduced read latency, but writes and failover remain dependent on primary-region behavior. |
| Regional service with remote recovery | The production service operates in one region while another region holds recoverable state. | Lower active infrastructure cost, but recovery time and recovery point depend on replication and restoration. |

The supplied programs register multiple regions and validate that regional workload placement does not accidentally cross region boundaries. They do not implement a complete cross-region database replication protocol. That omission is deliberate: geographic recovery requires a data-consistency and ownership model beyond replica placement.

### Data consistency and recovery

Recovery Point Objective (RPO) describes the maximum acceptable data loss measured in time. Recovery Time Objective (RTO) describes the target time to restore a service after a disruptive event.

Synchronous replication can reduce the amount of acknowledged data lost during failover, but can introduce latency and availability dependencies. Asynchronous replication can improve write latency and geographic distance tolerance, but a failover may lose recent writes that have not reached the recovery region.

A complete recovery plan should define:

- Which region is authoritative for writes.
- How replica lag is measured and constrained.
- How the system prevents two regions from independently accepting conflicting writes.
- How clients are redirected after a regional outage.
- How encryption keys, identity services, DNS, monitoring, and deployment credentials remain available.
- How restored replicas are checked for consistency before receiving production traffic.

The supplied reliability calculations assume independent failures. Real geographic systems have shared dependencies and correlated failures, so their results should not be treated as production availability guarantees.

## Availability and reliability models

For a series of independent components that must all work, end-to-end availability is the product of their individual availabilities:

\[
A_{\mathrm{series}}=\prod_{i=1}^{n} A_i
\]

If a service requires both an application and its database, each at 99% availability, the independent-series estimate is 98.01%.

For independent parallel replicas where at least one must work, availability is:

\[
A_{\mathrm{parallel}}=1-\prod_{i=1}^{n}(1-A_i)
\]

Two independent replicas with availability 99.9% each yield an estimated availability of 99.9999%, provided either replica can independently serve the required workload.

For three equal, independent zones with individual outage probability \(p\), a service requiring at least two healthy replicas remains available unless two or more zones fail. Its modeled availability is:

\[
A=(1-p)^3+3p(1-p)^2
\]

This expression is valid only under the stated assumptions. Correlated failures, shared databases, capacity constraints, routing dependencies, and insufficient failover headroom can reduce real availability.

The Python implementation includes analytical calculations and a seeded Monte Carlo simulation. The C++ and Java implementations calculate parallel availability, while the JavaScript implementation emphasizes event-driven state changes and workload health.

## Python implementation

The Python script uses dataclasses and enums to represent regions, zones, workloads, placement policies, and zone states.

`Infrastructure` validates topology relationships and placement constraints. `place_replicas` validates the complete placement before consuming zone capacity, reducing the risk of partial allocation when validation fails. `simulate_zone_failure` changes a zone's state and reports the effect on workloads.

The placement recommendation method sorts candidates by latency and avoids overlapping modeled failure domains. This is a constrained heuristic, not a globally optimal placement solver. It does not optimize cost, network bandwidth, or application-specific affinity.

The availability functions distinguish series dependencies from parallel replicas. The Monte Carlo simulation estimates service availability under a specified independent zone-outage probability. A fixed random seed makes the demonstration reproducible, while the unit tests verify availability calculations, invalid inputs, failure tolerance, and placement validation.

The report is serialized to JSON for inspection or integration into other operational tooling.

## JavaScript implementation

The JavaScript program models infrastructure as an event-driven control plane using Node.js's built-in `EventEmitter`.

`AvailabilityZone` maintains status and allocations. `Workload` computes healthy replicas from the current topology. `RegionalControlPlane` registers regions and workloads, evaluates placements, records audit events, and emits events when zone state changes.

The asynchronous `changeZoneStatus` method illustrates how an infrastructure controller can publish state changes and evaluate their impact on dependent services. The demonstration includes an event listener for workload availability loss.

Event emission is not itself failover. A production controller must handle duplicate events, delayed health checks, concurrent operations, stale observations, and retries. The program explicitly separates state evaluation from actual orchestration.

The placement algorithm favors healthy zones with distinct modeled failure domains and lower latency. It uses built-in assertions to validate behavior without requiring external packages.

## C++ case study

The C++ program models a regional order-processing service through a `GovernanceEngine`.

The engine owns region, zone, and workload registries using ordered maps. A workload specifies its desired replica count and minimum healthy threshold. Zones track allocated capacity and modeled failure domains.

The `place` method rejects duplicate zones, unknown identifiers, cross-region placement, unhealthy zones, insufficient capacity, and overlapping failure domains. Validation occurs before allocations are updated.

`simulateFailure` marks a zone as down and reports the remaining healthy replica count for every affected workload. The program also contrasts serial and parallel availability calculations.

The ordered maps provide predictable traversal and logarithmic key lookup. A more demanding implementation could use hash-based lookup, but placement would still need careful coordination when multiple scheduling operations compete for the same capacity.

The engine is an executable case study, not a distributed scheduler. Its state exists in one process and does not provide durable storage, concurrent allocation locks, real health checks, or automated traffic management.

## Java implementation

The Java implementation models the same infrastructure problem through enterprise-oriented domain types and an `InfrastructureService`.

Records provide immutable representations of region metadata and audit events. `AvailabilityZone` encapsulates capacity, state, and allocations. `Workload` contains replica requirements, placement state, and the service's minimum healthy threshold.

The `ReplicationPolicy` enum distinguishes single-zone and multi-zone placement. `placeWorkload` validates region ownership, replica count, zone uniqueness, zone health, capacity, and modeled failure-domain separation before recording a placement.

The service also provides deterministic candidate selection, workload-health evaluation, state-change auditing, and immutable snapshots of selected collections.

The audit records contain event identifiers, timestamps, event types, subjects, and details. A production audit system would normally persist these records, restrict modification, and associate administrative changes with authenticated identities.

The implementation uses standard Java 17 features and has no third-party dependencies.

## SQL relational model

The PostgreSQL script stores infrastructure topology and workload state in normalized relational tables.

| Table | Purpose |
|---|---|
| `regions` | Stores geographic and residency boundaries. |
| `availability_zones` | Stores zone health, capacity, region ownership, and latency estimates. |
| `failure_domains` | Describes modeled shared infrastructure dependencies. |
| `zone_failure_domains` | Associates each zone with one or more failure domains. |
| `workloads` | Stores replica requirements, region ownership, and replication policy. |
| `replica_placements` | Associates workloads with zones and records replica counts. |
| `zone_incidents` | Records outage, degradation, maintenance, and recovery events. |
| `regional_protection_policies` | Stores regional resilience requirements. |
| `infrastructure_audit` | Stores structured records of infrastructure operations. |

Primary keys prevent duplicate identities. Foreign keys ensure that placement records reference registered workloads and zones. Check constraints reject negative capacity, invalid replica thresholds, and invalid incident intervals.

The `validate_replica_placement` trigger checks region compatibility, workload policy, zone health, and available capacity. The capacity-maintenance trigger updates zone allocation counters when placements change. The workload replica-limit trigger prevents placements from exceeding the configured replica count.

`workload_health` calculates healthy and placed replica counts and evaluates the minimum healthy replica requirement. `zone_capacity_report` exposes capacity utilization and latency estimates for operational queries.

The incident demonstration marks a zone unavailable, records an incident and audit event, evaluates service health, and restores the zone. The transaction keeps these demonstration changes together.

The SQL constraints protect important invariants, but they do not constitute a complete concurrency-safe scheduling system. Concurrent placement transactions require appropriate row locking, isolation decisions, and retry handling. Additional controls are also necessary to prevent capacity updates and workload-policy changes from racing with placement operations.

## Distinguishing the resilience mechanisms

| Mechanism | Failure boundary | Primary concern |
|---|---|---|
| Zone isolation | A localized infrastructure location | Avoiding correlated failure within a region |
| Multi-zone replication | Several zones in one region | Continuing service after a zone outage |
| Geographic redundancy | Multiple regions | Recovering from broader geographic or regional disruption |
| Capacity headroom | Resource saturation during normal operation or failover | Ensuring surviving locations can handle redirected demand |
| Data replication | Storage and data consistency boundaries | Maintaining recoverable and usable application state |
| Traffic failover | Client and network routing boundaries | Directing requests to healthy service endpoints |

These mechanisms complement each other but cannot replace one another. Geographic redundancy does not automatically ensure that data is consistent. Multiple zones do not automatically protect a single-region database. Healthy replicas do not guarantee availability when the surviving capacity cannot handle production traffic.

## Failure scenarios and edge cases

**Single-zone deployment.** A workload with all replicas in one zone loses all replicas if that zone becomes unavailable. Increasing the replica count without changing placement does not solve this problem.

**Insufficient surviving capacity.** A three-zone workload may have enough replicas after one zone fails but still be unable to handle full production demand. Capacity planning must account for the expected failure scenario and the workload's resource requirements.

**Shared failure domains.** Zones with separate identifiers may share a network path, control plane, or other critical dependency. Placement checks can only enforce independence when those relationships are modeled accurately.

**Regional outage.** A multi-zone service within one region can remain unavailable if the entire region or a shared regional dependency fails. Recovery requires a separate regional deployment and a defined data and traffic strategy.

**Degraded zones.** A zone may remain reachable while operating with reduced capacity. Treating all reachable zones as fully healthy can cause overload during failover.

**Stale health information.** A controller may make placement or routing decisions using old observations. Health-state changes should be confirmed through appropriate checks, and operations should tolerate retries.

**Concurrent scheduling.** Two schedulers can both observe sufficient capacity and then over-allocate the same zone unless capacity reservations are coordinated transactionally.

**Data residency restrictions.** A technically valid cross-region deployment may violate legal, contractual, or organizational requirements. Geographic placement must consider residency rules as well as latency and fault tolerance.

**False independence assumptions.** Reliability formulas can substantially overestimate availability when failures are correlated. Shared infrastructure dependencies should be included in the model wherever credible data is available.

## Operational and production considerations

A production architecture needs explicit service-level objectives, measurable failure boundaries, and tested recovery procedures. The minimum healthy replica count is a useful state-modeling rule, but actual service readiness should include dependency health, request success rates, and capacity.

Capacity planning should consider CPU, memory, storage IOPS, network throughput, connection limits, and the extra demand created by traffic redistribution. Merely counting free replica slots is insufficient when different zones have different resource constraints.

Health monitoring should distinguish a zone outage from application failure, network partition, control-plane degradation, and regional failure. Automated recovery should include safe retries, idempotent operations, auditability, and protection against conflicting recovery actions.

Disaster recovery exercises should verify both infrastructure availability and data correctness. A recovered service that serves stale or inconsistent records is not necessarily a successful recovery.

The included implementations are intentionally self-contained simulations. They illustrate topology modeling, placement validation, failure-domain separation, availability estimation, health-state transitions, relational integrity, and auditing without claiming to replace a cloud provider's actual infrastructure controls.
