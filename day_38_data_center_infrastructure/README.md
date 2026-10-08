# Data Center Infrastructure: Servers, Racks, Power, Cooling, Redundancy, and Physical Networking

## Scope

This learning artifact models a physical data center as an interconnected set of capacity and failure domains.

The central distinction is important:

- **Servers** consume rack space, electrical power, cooling capacity, and network ports.
- **Racks** impose physical and electrical limits. A rack can have unused rack units while already being electrically constrained.
- **Power infrastructure** determines whether equipment can continue operating when an electrical path, feed, or upstream component fails.
- **Cooling infrastructure** removes the heat produced by IT equipment. Normal capacity is different from capacity available after a cooling failure.
- **Redundancy** concerns independence between failure domains. Two connections are not automatically redundant if they ultimately depend on the same upstream component.
- **Physical networking** connects servers through top-of-rack switches and requires separate paths when switch failure must be tolerated.

The implementations deliberately treat these as related but distinct engineering concerns.

## Core Physical Model

A useful simplified relationship is:

`IT electrical load ≈ IT thermal load`

A server consuming 1.5 kW of electrical power ultimately produces approximately 1.5 kW of heat that the facility must remove.

Rack planning therefore has several simultaneous constraints:

`Rack capacity = min(space capacity, electrical capacity, thermal capacity, network capacity)`

The minimum is not calculated as one universal number because the resources have different units and failure characteristics. A 42U rack may have 10U free while its power distribution is already at its safe operating limit.

The model uses the following major resources:

| Resource | Example constraint | Failure question |
|---|---|---|
| Server | Power and connectivity | Can the workload operate? |
| Rack | U-space and kW | Can additional equipment be installed? |
| Power feed | kW | Does one feed failure affect equipment? |
| Cooling system | Thermal kW | Can heat still be removed after failure? |
| Network switch | Port capacity | Does switch failure remove connectivity? |

## Server Infrastructure

The Python implementation represents a server with its rack, electrical demand, cooling demand, network ports, power-path configuration, and operational state.

The `Server` class is intentionally small because the important engineering behavior belongs in the systems that consume server attributes.

The Python model distinguishes:

- running servers,
- failed servers,
- maintenance servers,
- single-path electrical equipment,
- equipment using a specified electrical path,
- dual network connections.

The Java implementation extends this idea with an explicit `ServerSpec`, `ServerState`, and `EquipmentRole`. This separates the immutable description of equipment from its current operational state.

The Java state transition logic prevents a failed server from being marked as running directly. A real operational system would normally require a recovery or validation procedure before returning failed equipment to service.

## Rack Engineering

A rack is not simply a cabinet with a maximum number of servers.

The implementations model two important rack constraints:

`used U < rack U capacity`

and

`installed power <= rack power capacity`

The Python example uses 42U racks with an 8 kW electrical limit. The C++ case study uses the same physical constraints while keeping the implementation strongly typed.

This demonstrates why rack planning should consider power density. If a server consumes 0.8 kW and a rack has an 8 kW limit, the electrical constraint may be reached before the physical 42U limit.

The capacity-planning function therefore calculates the number of racks using the tighter resource rather than assuming every rack can simply hold 42 servers.

### Rack-level failure and planning implications

A rack can become a localized failure domain. Equipment installed in the same rack may share:

- physical space,
- rack power distribution,
- environmental conditions,
- top-of-rack networking,
- cabling routes.

For highly available workloads, distributing servers across independent racks can reduce the impact of a rack-level failure.

## Power Infrastructure

The examples use power paths `A` and `B`.

A dual-path architecture is meaningful only when the paths remain independent beyond the server's power supply. Independence may need to extend through:

`server PSU -> PDU -> UPS -> electrical panel -> transformer -> generator`

The code does not pretend to model every component in this chain. Instead, it explicitly identifies the point where the simplified model begins.

The Python implementation can test the effect of losing a power feed and identify single-fed equipment that would be exposed.

The Java implementation represents power configuration with an enum and evaluates whether a server has an alternate path.

The SQL model stores individual server-to-power-feed allocations. This is more useful than storing only a Boolean such as `is_redundant`, because the database can show which physical feed carries the allocation.

### Power capacity

Power capacity must be evaluated per failure domain.

A facility may have enough aggregate capacity while one feed is overloaded. For example:

`A = 9.5 kW / 10 kW`

`B = 3 kW / 10 kW`

The aggregate is acceptable, but feed A has very little remaining headroom.

A design that requires surviving feed A failure must also establish that the surviving path can carry the required load.

## Cooling Infrastructure

Cooling is modeled separately from power.

The simplified model uses server electrical consumption as its thermal load:

`thermal load = server power consumption`

This is appropriate for a capacity-planning demonstration because the majority of electrical energy consumed by IT equipment becomes heat.

The Python, JavaScript, C++, and Java implementations include two cooling systems. The failure analysis asks whether the remaining cooling capacity is sufficient for the active IT load.

This is different from asking whether the cooling plant has enough capacity during normal operation.

For example:

`Normal cooling capacity = 24 kW`

`Normal IT heat load = 7 kW`

A single cooling unit rated at 12 kW may fail safely if another independent 12 kW unit remains available.

If the active load were 15 kW, the same failure would leave only 12 kW and would therefore be insufficient.

## Redundancy and Failure Domains

Redundancy is not simply duplication.

Two devices are redundant only when the failure of one does not remove the required service path.

Examples include:

- two power feeds supplied from genuinely independent upstream paths,
- two network connections terminating on different switches,
- multiple cooling units with sufficient remaining capacity,
- multiple physical routes for critical cabling.

The implementations intentionally test failure conditions rather than merely storing a redundancy flag.

A useful engineering question is:

> What single component can still remove both supposedly redundant paths?

If both power supplies depend on the same PDU, the two power cords do not provide full power-path independence.

If both network links terminate on the same top-of-rack switch, two Ethernet cables do not provide switch-level redundancy.

## Physical Networking

The JavaScript, C++, Java, and SQL implementations model top-of-rack switches.

A server with two network connections is connected to:

- `TOR-A`
- `TOR-B`

This gives the model a concrete failure-domain boundary.

The SQL schema represents each physical server-to-switch relationship in `server_network_connection`.

That structure permits queries such as identifying servers connected to fewer than two switches.

The model does not claim that two top-of-rack connections automatically provide end-to-end network availability. Upstream switches, aggregation layers, routers, routing protocols, cabling, and power dependencies can introduce additional failure domains.

## Python Implementation

The Python program provides the broadest simulation-oriented model.

The major components are:

- `Server` for IT equipment characteristics.
- `Rack` for U-space and electrical constraints.
- `PowerFeed` for electrical capacity.
- `CoolingSystem` for thermal capacity.
- `NetworkSwitch` for physical port capacity.
- `DataCenter` for orchestration and failure analysis.

The `install_server()` operation validates rack existence, rack capacity, power capacity, cooling capacity, and network connectivity before adding equipment.

The script also calculates a simplified PUE value:

`PUE = total facility energy / total IT energy`

The demonstration uses facility overhead as an explicit input rather than pretending that PUE can be inferred from rack information alone.

## JavaScript Implementation

The JavaScript implementation emphasizes event-oriented resource objects and runtime validation.

Its `DataCenter`, `PowerSystem`, `CoolingSystem`, and `NetworkFabric` classes divide responsibilities by physical subsystem.

JavaScript's `Map`, `Set`, object structures, getters, and custom error classes are used to represent dynamic infrastructure state.

The `PowerSystem` uses a `Set` of power paths for each server. A dual-path server can therefore be tested without relying on a textual property such as `"redundant": true`.

The custom `CapacityError` distinguishes capacity failures from general infrastructure validation failures.

The network model treats a second top-of-rack connection as a distinct physical path rather than simply counting two ports on one switch.

## C++ Case Study

The C++ implementation is structured as a capacity and failure-domain engine.

`Rack` owns the rack-level resource calculations.

`PowerFeed` enforces electrical capacity.

`CoolingSystem` enforces thermal capacity.

`NetworkFabric` models top-of-rack port consumption.

`DataCenter` coordinates the physical systems.

The use of strong types such as `enum class PowerPath` and `enum class ServerState` prevents many accidental string-based state errors.

The `MergeStyleCapacityPlanner` is intentionally a capacity-planning component rather than a generic algorithm exercise. It determines the minimum rack count by comparing the physical U limit with the electrical rack limit.

For a server count `N`, server power `P`, and rack power limit `R`, the power-based server count per rack is approximately:

`floor(R / P)`

The actual number of servers per rack is constrained by both that result and the rack's U capacity.

The program also demonstrates exception-based rejection of invalid infrastructure states.

## Java Enterprise Model

The Java implementation uses explicit domain types to model enterprise infrastructure.

Important types include:

- `ServerSpec`
- `Server`
- `Rack`
- `PowerSystem`
- `CoolingPlant`
- `NetworkFabric`
- `Repository`

The name `Repository` represents the modeled infrastructure inventory rather than a software source-code repository.

Java enums make infrastructure states and equipment roles explicit.

`ServerState` distinguishes running, failed, and maintenance conditions.

`EquipmentRole` distinguishes application, database, backup, and network-oriented equipment.

The provisioning service validates rack existence, rack capacity, electrical allocation, cooling allocation, and network connectivity before finalizing installation.

This structure demonstrates why enterprise infrastructure systems benefit from separating domain rules instead of placing every rule in one large conditional block.

## PostgreSQL Data Model

The SQL implementation provides the most explicit relational representation.

The core relationships are:

`data_center -> rack -> server`

and:

`server -> server_power_feed -> power_feed`

`server -> server_network_connection -> network_switch`

`server -> server_cooling_assignment -> cooling_system`

This design represents physical relationships directly.

### Database constraints

The schema uses:

- primary keys for entity identity,
- foreign keys for physical relationships,
- unique constraints for equipment names,
- check constraints for positive capacity values,
- an enum for server state,
- an enum for power configuration.

The constraints prevent structurally invalid data such as negative server power or zero-capacity racks.

### Power allocations

A server's power-feed relationship is stored in a junction table because a server can have multiple electrical feeds.

This is more expressive than placing `power_feed = 'A'` directly in the server table.

A dual-fed server can therefore have separate allocations associated with feeds A and B.

### Network connections

The `server_network_connection` table records each physical connection.

The unique constraint on:

`(network_switch_id, port_number)`

prevents two servers from being assigned the same physical switch port.

### Cooling assignments

The `server_cooling_assignment` table associates thermal load with cooling equipment.

This allows cooling capacity to be queried and compared against actual active server load.

## Capacity Queries

The SQL script includes queries for:

- rack U utilization,
- rack electrical utilization,
- power-feed utilization,
- cooling utilization,
- network redundancy exposure,
- power-feed failure impact,
- cooling failure survivability,
- PUE calculation,
- capacity snapshots.

These queries are intentionally based on relationships between physical entities rather than static documentation.

For example, a rack's installed power is calculated from its active servers. The value does not have to be manually maintained in a separate rack field.

## Transactional Capacity Change

The SQL script demonstrates a transaction that temporarily changes a rack's power capacity to an unsafe value.

The resulting state is queried and identified as a capacity violation.

The transaction is then rolled back.

This illustrates an important database principle: an infrastructure inventory should not retain a configuration change merely because an individual field update was syntactically valid.

Application-level validation and database-level integrity serve different purposes. The application can provide operational workflow, while database constraints protect structural consistency.

## Failure Analysis

The examples distinguish several failure types.

### Power-feed failure

A power-feed failure tests whether a server has another valid electrical path.

The key distinction is between:

`single-path equipment`

and

`dual-path equipment`

A server with two power connections is not automatically resilient unless those connections terminate in independent electrical domains.

### Cooling failure

Cooling failure is capacity-based.

The question is not simply whether another cooling unit exists. The surviving capacity must be compared with the active thermal load.

### Network switch failure

Network resilience depends on physical connection diversity.

The examples use two top-of-rack switches. A server connected only to one switch is exposed to that switch's failure.

A dual-connected server has an alternate physical path, assuming the upstream network remains available.

## Edge Cases and Failure Conditions

The implementations intentionally reject several unsafe states.

A server cannot have negative or zero power consumption.

A rack cannot have non-positive capacity.

A server cannot be installed into a nonexistent rack.

A rack cannot accept equipment when its U-space is exhausted.

A rack cannot accept equipment when its electrical capacity is exceeded.

A power feed cannot accept allocations beyond its configured capacity.

A cooling system cannot accept thermal load beyond its capacity.

A network switch cannot accept more physical connections than its port capacity.

The SQL model also prevents references to nonexistent physical equipment through foreign keys.

## Common Modeling Mistakes

### Treating rack space as the only capacity metric

A 42U rack does not imply that 42 arbitrary servers can be installed. High-density servers may exhaust electrical or cooling capacity first.

### Treating two power cords as complete redundancy

Two power cords connected to one upstream failure domain provide limited redundancy.

### Treating two network cables as switch redundancy

Two cables connected to the same switch still share the switch failure domain.

### Evaluating only normal operating conditions

A system with sufficient capacity during normal operation may fail after one cooling unit, power path, or network switch becomes unavailable.

### Storing derived capacity values without a source relationship

If rack power utilization is manually stored, it can become inconsistent with actual installed servers. Relational calculations based on equipment records provide a stronger source of truth.

## Performance Considerations

Capacity queries over a large facility can involve joins across millions of infrastructure records.

The SQL implementation therefore adds indexes on frequently traversed relationships such as:

`rack(data_center_id)`

`server(rack_id)`

`power_feed(data_center_id)`

`cooling_system(data_center_id)`

`network_switch(data_center_id)`

A partial index for running servers is useful when operational queries overwhelmingly focus on currently active equipment.

The application implementations use maps and hash-based collections where identity lookup is required. This avoids repeatedly scanning every rack to locate a named resource.

## Security and Operational Considerations

Physical infrastructure information can be sensitive because it can expose:

- server locations,
- power architecture,
- network topology,
- equipment roles,
- capacity headroom,
- redundancy weaknesses.

Production infrastructure systems should therefore enforce authorization around inventory changes and failure simulations.

Audit trails should record who changed:

- equipment state,
- rack assignments,
- power assignments,
- cooling assignments,
- network connections,
- capacity limits.

A production database should also separate operational permissions from read-only reporting permissions.

The examples intentionally do not include credentials, secrets, network passwords, or real infrastructure addresses.

## Production Design Considerations

A production data center management platform would normally need more detailed models for:

- UPS systems,
- generators,
- automatic transfer switches,
- PDUs,
- transformers,
- electrical circuits,
- environmental sensors,
- temperature zones,
- humidity,
- airflow,
- hot-aisle and cold-aisle layouts,
- cable paths,
- patch panels,
- aggregation switches,
- routers,
- firewalls,
- maintenance windows,
- equipment lifecycle,
- capacity reservations,
- alarms,
- telemetry,
- incident history.

The presented models intentionally stop at a level where the relationships between servers, racks, power, cooling, redundancy, and physical networking remain clear and executable.

The central engineering principle remains consistent across all six implementations: **data center availability is a property of interconnected physical systems and their failure domains, not of server count alone.**
