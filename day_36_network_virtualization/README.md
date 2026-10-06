# Network Virtualization: Virtual Switches, Virtual Networks, Overlays, and SDN

## Scope

This learning artifact models network virtualization as a software-defined abstraction over physical networking.

The implementations treat four closely related mechanisms as distinct:

- **Virtual switches** provide logical Layer-2 forwarding between virtual interfaces.
- **Virtual networks** provide logical segmentation, addressing, VLAN identity, and tenant or workload boundaries.
- **Overlay networks** allow a logical network to span an independent underlay by carrying tenant traffic through an encapsulation layer such as VXLAN.
- **Software-defined networking** separates centralized control-plane intent from distributed data-plane forwarding behavior.

The examples use a small virtual data-center topology containing frontend, backend, and database segments. Traffic is deliberately exercised both within a logical segment and across Layer-3 boundaries.

## Core Network Virtualization Model

Traditional networking associates forwarding behavior closely with physical interfaces, switches, routers, and cabling. Network virtualization moves part of that topology into software-defined objects.

A virtual machine can have a virtual NIC with its own MAC address and IP address. That NIC can connect to a virtual switch port. The virtual switch can maintain a forwarding table without requiring a physical Ethernet switch for every logical connection.

A virtual network adds another abstraction. It defines a logical subnet, gateway, VLAN identity, or overlay identifier. Multiple virtual networks can coexist on the same physical infrastructure while remaining logically separated.

The important distinction is that virtualization does not eliminate the underlying network. It introduces a logical network layer that uses the physical infrastructure as an underlay.

A useful conceptual relationship is:

`VM -> vNIC -> virtual switch -> virtual network -> optional overlay -> physical underlay`

When Layer-3 communication is required, the path can instead become:

`VM -> vNIC -> virtual switch -> virtual router -> destination virtual network`

With an overlay, the logical packet may travel as:

`inner Ethernet frame -> overlay encapsulation -> underlay transport -> decapsulation -> destination virtual network`

## Virtual Switches

A virtual switch is a software implementation of Ethernet-switching behavior.

The most important operation demonstrated by the implementations is MAC learning.

When a frame enters a virtual switch, the switch records the source MAC address against the ingress port. When a destination MAC address is already known, the switch can send the frame directly to the associated port.

For an unknown destination, the switch floods the frame to eligible ports other than the ingress port.

The Python implementation exposes this behavior through `VirtualSwitch.receive()`. The JavaScript implementation represents the same operational mechanism with an event-driven `VirtualSwitch`. The C++ case study stores learned addresses in an ordered forwarding table, while the Java implementation keeps forwarding state inside an enterprise-oriented domain class.

The forwarding table is fundamentally data-plane state. It answers the operational question:

`Where should this Ethernet frame go?`

It does not by itself define the business or security policy governing which networks are allowed to communicate.

### MAC learning

The simplified learning process is:

`source MAC -> ingress port`

A later frame destined for that source can then use the learned association.

The examples intentionally send traffic in both directions. The first frame may be flooded because the destination has not yet been learned. Once a response enters from another port, the switch learns the response source and can use the resulting table for more precise forwarding.

The forwarding table contains entries such as:

`02:00:00:00:20:01 -> app-port`

A production virtual switch has substantially more state and behavior, including VLAN membership, broadcast domains, aging, port security, multicast handling, QoS, filtering, tunneling, and hardware or kernel acceleration.

## Virtual Networks

A virtual network defines a logical communication domain.

The examples create:

| Network | Subnet | VLAN | VNI | Purpose |
|---|---|---:|---:|---|
| frontend | 10.10.10.0/24 | 110 | 5001 | Web-facing workloads |
| backend | 10.10.20.0/24 | 120 | 5002 | Application services |
| database | 10.10.30.0/24 | 130 | 5003 | Isolated data services |

The VLAN identifier is a Layer-2 segmentation identifier. The VNI is an overlay segmentation identifier.

These identifiers are not interchangeable.

A VLAN traditionally identifies a Layer-2 broadcast domain within a switching environment. VXLAN uses a 24-bit VNI to identify an overlay segment and therefore provides a much larger logical namespace.

The database network is marked as isolated in the examples. Isolation is not created merely by assigning a different subnet. The SDN policy and routing logic must also prevent unauthorized traffic from crossing the Layer-3 boundary.

## Virtual NICs

A virtual NIC gives a virtual machine a logical network attachment.

Each example associates a NIC with:

- a MAC address
- an IP address
- a virtual network
- a virtual switch port where appropriate

For example, the simulated web workload uses:

`MAC: 02:00:00:00:10:01`

`IP: 10.10.10.10`

`Network: frontend`

The application workload uses a different logical network:

`MAC: 02:00:00:00:20:01`

`IP: 10.10.20.10`

`Network: backend`

This allows the same underlying compute host to contain workloads belonging to different logical networks.

## VLAN-Style Segmentation

The Python and Java implementations associate VLAN IDs with virtual networks, while the SQL model stores VLAN identity as a constrained integer.

Valid VLAN IDs in the model are between 1 and 4094.

The VLAN value is deliberately constrained because a virtual network should not silently accept invalid Layer-2 segmentation identifiers.

The SQL schema uses:

`CHECK (vlan_id BETWEEN 1 AND 4094)`

This demonstrates an important database principle: structural network metadata should be validated as close to its source of truth as practical.

A VLAN provides segmentation, but segmentation does not automatically mean application-layer authorization. Routing and security policy are separate mechanisms.

## Layer-3 Virtual Routing

When the source and destination belong to different virtual networks, Layer-3 routing becomes necessary.

The example:

`frontend -> backend`

is permitted.

The example:

`frontend -> database`

is denied.

The virtual router first identifies the destination network from the destination IP address.

The implementations use longest-prefix matching when selecting among candidate network prefixes. This matters because routing systems may contain overlapping prefixes, and the most specific matching route normally has precedence.

After identifying the destination network, the router consults the SDN policy engine.

The route therefore has two conceptually different responsibilities:

- determine where the destination belongs
- determine whether the source is permitted to communicate with that destination

The router is not merely a packet transporter. In a virtualized architecture it becomes one of the points where logical network boundaries are enforced.

## Overlay Networks

An overlay creates a logical network on top of an independent transport network.

The examples use a VXLAN-style abstraction.

An inner Ethernet frame contains tenant information such as:

`02:00:00:00:10:01 -> 02:00:00:00:20:01`

The overlay adds outer transport information such as:

`192.0.2.10 -> 192.0.2.20`

and a VNI:

`5001`

The conceptual structure is:

`Outer transport header`

`VXLAN-like identifier`

`Inner Ethernet frame`

The underlay needs to understand how to transport the outer packet. It does not need to understand every tenant's internal Ethernet addressing.

That separation is one of the major architectural advantages of overlays.

### VNI versus VLAN

A VLAN ID is limited to the traditional VLAN identifier space. A VXLAN VNI is 24 bits, allowing a much larger logical segment namespace.

The database schema therefore constrains VNIs separately from VLAN IDs.

The Python, JavaScript, C++, and Java implementations also reject values outside the valid 24-bit VNI range.

## Encapsulation and Decapsulation

Encapsulation occurs at an overlay tunnel endpoint.

The inner frame is preserved while outer transport metadata is added.

For example:

`inner source = web MAC`

`inner destination = application MAC`

becomes something conceptually similar to:

`outer source VTEP = 192.0.2.10`

`outer destination VTEP = 192.0.2.20`

`VNI = 5001`

At the receiving endpoint, the VNI is checked and the inner frame is recovered.

The implementations deliberately reject VNI mismatches. This models the fact that an overlay packet associated with one logical segment should not automatically become traffic for another segment.

## Software-Defined Networking

Software-defined networking introduces a strong separation between control-plane decisions and data-plane execution.

The examples model an SDN controller or policy engine that stores desired network behavior.

The controller decides policy such as:

`frontend -> backend = ALLOW`

`frontend -> database = DENY`

The virtual switch still performs the immediate forwarding operation.

This creates a useful distinction:

| Plane | Responsibility |
|---|---|
| Control plane | topology, policy, routes, desired forwarding behavior |
| Data plane | packet forwarding, MAC learning, packet handling |

The JavaScript implementation makes this distinction particularly visible because the controller is event-driven. Port changes and packet drops generate events that the controller can observe and reconcile.

The Python implementation represents the controller explicitly through `SDNController`.

The C++ implementation separates `SDNPolicyEngine` from `VirtualSwitch`.

The Java implementation uses `NetworkPolicyEngine` and `VirtualSwitch` as separate domain components.

## SDN Policy

The policy engine models logical communication relationships rather than individual Ethernet forwarding decisions.

The configured policy permits:

`frontend -> backend`

`backend -> frontend`

`backend -> database`

`database -> backend`

The policy denies:

`frontend -> database`

`database -> frontend`

An omitted policy defaults to deny in the Python, C++, and Java models.

This default-deny behavior prevents an unknown relationship from silently becoming permitted.

The policy model also demonstrates why network segmentation and policy enforcement should not be treated as the same concept.

Two workloads can exist in different subnets and still be routable. The security policy determines whether that routed communication is permitted.

## Branching of the Data Path

The simulated traffic produces several different paths.

### Same logical network

A web workload and another workload within the same Layer-2 segment can communicate through the virtual switch.

The virtual switch uses MAC learning and forwarding.

### Different logical networks

Frontend traffic destined for the backend crosses a Layer-3 boundary.

The virtual router identifies the backend subnet and evaluates policy before forwarding.

### Different overlay endpoints

When the destination logical network exists behind another tunnel endpoint, the inner frame is encapsulated and carried across the underlay.

The remote endpoint decapsulates the traffic before it reaches the destination virtual switch or virtual network.

## Python Implementation

The Python program is a complete simulation centered on explicit network-domain objects.

`VirtualNIC` represents a logical host attachment.

`VirtualNetwork` models subnet, VLAN, VNI, gateway, and isolation properties.

`VirtualSwitch` contains ports, a MAC learning table, forwarding state, and packet counters.

`VirtualRouter` performs destination-network discovery and policy enforcement.

`OverlayNetwork` models VNI-based encapsulation and decapsulation.

`SDNController` represents the control-plane layer.

The `NetworkLab` class assembles these components into a small data-center topology.

The executable demonstrations include MAC learning, Layer-3 routing, overlay encapsulation, policy denial, and a disabled virtual-port failure.

The validation code also demonstrates invalid MAC addresses and invalid VNI values as explicit failures rather than silently accepting malformed network metadata.

## JavaScript Implementation

The JavaScript implementation takes an event-driven approach.

`VirtualSwitch` extends `EventEmitter`, which makes operational state changes observable.

The switch emits events for:

- forwarding
- flooding
- packet drops
- port-state changes

The `SDNController` listens to topology and data-plane events. Its asynchronous `reconcile()` method models the idea of a controller periodically reconciling observed state against intended state.

This is deliberately different from the Python implementation. JavaScript emphasizes event propagation and asynchronous control behavior rather than primarily modeling the network as synchronous objects.

The `OverlayTunnel` models outer transport metadata and an inner Ethernet frame. The VNI is validated during decapsulation.

The JavaScript implementation also validates IPv4 addresses and CIDR membership instead of treating addresses as arbitrary strings.

## C++ Case Study

The C++ program models a virtualized data-center fabric.

Its architecture consists of:

`NetworkFabric`

`VirtualSwitch`

`VirtualRouter`

`SDNPolicyEngine`

`OverlayFabric`

The `VirtualSwitch` uses an ordered map to associate MAC addresses with virtual ports.

The router performs longest-prefix matching by comparing prefix lengths when several virtual networks contain a destination address.

The overlay fabric maintains an endpoint database mapping MAC addresses to virtual tunnel endpoints.

The C++ implementation uses strong separation of concerns because forwarding, policy, routing, and overlay state have different operational responsibilities.

The case study also tracks forwarded, flooded, and dropped frames. This is useful because a network model that only reports successful traffic hides the operational information required for diagnosing failures.

C++ exception handling is used for malformed network configuration, invalid addresses, invalid VNIs, unknown switch ports, and overlay mismatches.

## Java Implementation

The Java implementation uses explicit domain types and enterprise-style services.

`VirtualNetwork` is represented as an immutable record containing network identity, type, subnet, VLAN, VNI, gateway, and isolation state.

`VirtualNic`, `VirtualMachine`, `EthernetFrame`, and `OverlayPacket` similarly represent domain entities.

The `NetworkPolicyEngine` owns policy registration and detects conflicting policy decisions for the same source and destination relationship.

The `VirtualSwitch` owns MAC-learning state and forwarding counters.

The `VirtualRouter` performs destination-network lookup and policy enforcement.

The `OverlayFabric` owns overlay endpoint resolution and VNI validation.

The design uses Java records for immutable value-oriented network objects and ordinary classes for components that maintain mutable operational state.

Security failures use `SecurityException`, while invalid lifecycle or configuration states use other runtime exceptions.

This distinction allows the application to differentiate between malformed configuration, unavailable resources, and an explicit network-policy denial.

## SQL Data Model

The PostgreSQL schema represents the network topology relationally.

The central entities are:

`virtual_network`

`virtual_switch`

`virtual_port`

`virtual_machine`

`virtual_nic`

`overlay_endpoint`

`overlay_mac_location`

`sdn_policy`

`mac_forwarding_entry`

`packet_event`

Foreign keys connect these entities into an operational model.

A virtual NIC belongs to a virtual machine and a virtual network. It can also be attached to a virtual switch port.

A virtual port belongs to a virtual switch.

An overlay endpoint belongs to a virtual network.

A forwarding entry belongs to a switch and points to an output port.

This relational structure makes the relationship between logical topology and operational forwarding state explicit.

## Database Constraints

The SQL script uses database constraints for network invariants.

VLAN IDs are restricted to 1 through 4094.

VNIs are restricted to the 24-bit VXLAN range.

IPv4 gateways are required to belong to their declared subnet.

MAC addresses are stored using PostgreSQL's `MACADDR` type.

Network types, policy actions, port states, and packet outcomes use PostgreSQL enums.

Foreign keys prevent orphaned NICs, ports, switches, networks, and policy records.

Unique constraints prevent duplicate VLAN IDs, VNIs, MAC addresses, IP addresses, and forwarding entries.

These constraints are valuable because an application should not be the only layer responsible for preserving network topology integrity.

## SQL Policy Evaluation

The `sdn_policy` table represents relationships between source and destination virtual networks.

The script uses a window function to determine the highest-priority rule for a source-destination pair.

This demonstrates how a relational database can model policy precedence rather than simply storing a single boolean permission.

A policy row contains:

`source_network_id`

`destination_network_id`

`action`

`priority`

`description`

The priority value allows multiple candidate policies to coexist while a query determines the effective rule.

## SQL Forwarding State

`mac_forwarding_entry` models the learned forwarding database of a virtual switch.

Its lookup key includes:

`switch_id`

`vlan_id`

`mac_address`

The corresponding output port tells the switch where traffic should be forwarded.

Indexes are created around this lookup because MAC forwarding is a high-frequency operation.

The query using `EXPLAIN (ANALYZE, BUFFERS)` demonstrates the database-performance perspective of this model.

A production network device would normally use specialized high-performance data structures rather than PostgreSQL for packet-by-packet forwarding. The SQL model is therefore an inventory, control, telemetry, or configuration representation rather than a literal replacement for a switch datapath.

## Overlay Endpoint Database

The overlay endpoint model separates logical network identity from underlay location.

A virtual network has a VNI.

An overlay endpoint has an underlay IP.

A MAC-location record associates a logical endpoint with an overlay endpoint.

This allows a query to answer:

`Which underlay endpoint currently hosts the logical destination MAC?`

That is a central concept in distributed overlay networks.

## Failure Handling

The implementations deliberately introduce a disabled virtual switch port.

When the application port is down, the switch cannot deliver the frame to that port.

The Python and Java programs restore the port after the failure demonstration.

The JavaScript implementation emits an event when the port changes state and allows the controller to reconcile the resulting topology.

The SQL model stores port state so operational queries can locate disabled ports.

This demonstrates a practical distinction between configuration state and observed forwarding behavior. A network can have a correct logical topology while still being unable to forward traffic because an individual dataplane component is unavailable.

## Security Boundaries

The database network is marked as isolated.

Isolation is implemented through explicit SDN policy rather than merely through naming or subnet assignment.

The policy denies direct:

`frontend -> database`

traffic.

The backend network is allowed to access the database network.

This produces a common layered architecture:

`frontend -> backend -> database`

rather than:

`frontend -> database`

The policy is enforced after destination-network identification, which makes the relationship between routing and access control explicit.

Production environments would normally extend this model with stateful firewalling, identity-aware policy, service-level authorization, logging, encryption, micro-segmentation, and more detailed protocol and port rules.

## Common Failure Modes

A virtualized network can fail even when the IP configuration appears correct.

A missing MAC-learning entry can cause unknown-unicast flooding.

A disabled virtual switch port can prevent delivery.

A missing route can make a destination unreachable.

An incorrect VNI can place traffic into the wrong logical overlay or cause decapsulation to fail.

An unavailable tunnel endpoint can break communication between logical networks hosted on different underlay nodes.

An incorrect policy can block valid traffic or permit traffic that should remain isolated.

A stale endpoint database can point traffic toward an old tunnel location.

A TTL reaching zero prevents continued Layer-3 forwarding.

The implementations intentionally expose several of these states rather than assuming all traffic succeeds.

## Performance Considerations

Virtual switching introduces software processing overhead compared with specialized physical forwarding hardware, although modern systems can accelerate virtual networking through kernel facilities, smart NICs, eBPF, DPDK, SR-IOV, hardware offload, and other mechanisms.

MAC lookup should be efficient because forwarding decisions occur frequently.

Overlay encapsulation adds headers and therefore consumes additional bandwidth and processing capacity.

The larger logical namespace provided by VXLAN comes with additional control-plane and endpoint-discovery complexity.

Centralized SDN control can simplify policy management, but controller availability and convergence become operational considerations.

A production architecture therefore needs to distinguish between:

`control-plane scalability`

and

`data-plane throughput`

A controller does not normally process every packet individually. It programs or influences forwarding behavior while the dataplane handles traffic at high frequency.

## Security Considerations

Network virtualization creates logical boundaries, but logical boundaries must be explicitly enforced.

Important security properties include:

- Strong separation of tenant or workload networks.
- Default-deny behavior for unknown network relationships.
- Validation of VLAN and VNI identifiers.
- Protection against spoofed MAC addresses.
- Protection against unauthorized tunnel endpoint registration.
- Authentication and authorization for SDN control-plane operations.
- Logging of denied and anomalous traffic.
- Protection of management networks from workload networks.
- Careful handling of stale forwarding and overlay endpoint state.
- Monitoring for unusual flooding or broadcast behavior.

An overlay should not be treated as encryption merely because it encapsulates traffic. Encapsulation and confidentiality are different properties.

## Operational Debugging

A useful troubleshooting sequence follows the path of the traffic.

First verify that the virtual NIC is enabled and has the expected MAC and IP configuration.

Then verify that the virtual switch port is operational.

Then inspect the MAC forwarding table.

If the destination belongs to another network, inspect the routing table and destination subnet.

Next inspect SDN policy.

If an overlay is involved, verify the VNI and both tunnel endpoints.

Finally inspect packet telemetry and counters for drops, flooding, and forwarding failures.

The artifacts expose these layers through switch counters, MAC tables, policy queries, overlay endpoint data, packet events, and disabled-port queries.

## Practical Architecture

The complete model can be viewed as a layered system:

`Workload`

`Virtual NIC`

`Virtual Switch`

`Virtual Network`

`Virtual Router / SDN Policy`

`Overlay Tunnel`

`Physical Underlay`

Each layer answers a different question.

The virtual NIC answers:

`Which logical interface belongs to this workload?`

The virtual switch answers:

`Which local port should receive this Ethernet frame?`

The virtual network answers:

`Which logical segment does this workload belong to?`

The router answers:

`Which logical network contains this destination?`

The policy engine answers:

`Is this source allowed to communicate with this destination?`

The overlay answers:

`How can this logical segment be transported across an independent underlay?`

The underlay answers:

`How do the physical or routed transport endpoints communicate?`

Keeping these responsibilities distinct is essential for designing and troubleshooting virtualized networks.

## Relationship Between Virtualization, Overlays, and SDN

These technologies solve different problems.

Network virtualization abstracts physical network resources into logical networks.

Virtual switching implements logical Layer-2 connectivity.

Overlay networking allows logical segments to extend across an underlay.

SDN provides a programmable control model for managing topology and forwarding policy.

An overlay does not automatically imply SDN.

SDN does not require VXLAN.

A virtual switch does not automatically provide inter-network routing.

A VLAN is not equivalent to a VNI.

A routing decision is not the same as an authorization decision.

Understanding these distinctions prevents architectural concepts from being collapsed into one generic idea of "virtual networking."

## Implementation Mapping

| Concern | Python | JavaScript | C++ | Java | PostgreSQL |
|---|---|---|---|---|---|
| Virtual switch | `VirtualSwitch` | `VirtualSwitch` | `VirtualSwitch` | `VirtualSwitch` | `mac_forwarding_entry` |
| Virtual network | `VirtualNetwork` | `VirtualNetwork` | `VirtualNetwork` | `VirtualNetwork` | `virtual_network` |
| Virtual NIC | `VirtualNIC` | `VirtualNIC` | `VirtualNIC` | `VirtualNic` | `virtual_nic` |
| Routing | `VirtualRouter` | `VirtualRouter` | `VirtualRouter` | `VirtualRouter` | policy and network queries |
| SDN control | `SDNController` | `SDNController` | `SDNPolicyEngine` | `NetworkPolicyEngine` | `sdn_policy` |
| Overlay | `OverlayNetwork` | `OverlayTunnel` | `OverlayFabric` | `OverlayFabric` | `overlay_endpoint` |
| Packet telemetry | counters and output | events and statistics | counters | switch statistics | `packet_event` |
| Failure state | disabled port | emitted port event | disabled port | `PortState.DOWN` | `port_state` |

The implementations intentionally use different programming models while preserving the same network architecture. This makes the technical concepts transferable without making the source files simple translations of one another.
