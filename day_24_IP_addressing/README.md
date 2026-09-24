# IP Addressing: IPv4, IPv6, Public IP, Private IP, Reserved Addresses, and IP Allocation

## Topic introduction

IP addressing is the system used to identify network interfaces and determine where IP packets should be delivered. Internet Protocol addressing is central to routing, subnetting, network segmentation, address allocation, NAT, network security, and dual-stack networking.

This study covers IPv4 and IPv6, including public and private addressing, special-purpose and reserved address ranges, CIDR notation, subnet masks, VLSM, address allocation, routing decisions, NAT, IPv6 prefixes, IPv6 address types, SLAAC-style address construction, validation, and practical address planning.

The three implementations approach the subject differently:

- Python provides a broad educational implementation using the standard `ipaddress` library. It is particularly useful for address parsing, network calculations, classification, allocation simulations, validation, and testing.
- JavaScript implements important IPv4 calculations directly and adds an educational IPv6 parser, making the underlying arithmetic and representation mechanisms visible without an external package.
- C++ develops an industry-style dual-stack enterprise network case study using custom IPv4 and IPv6 classes, allocation logic, routing, NAT simulation, validation, and an address inventory.

The examples use documentation address ranges where addresses are needed for demonstrations. They are not intended to represent real production public services.

## Fundamental concepts

### What is an IP address?

An IP address is a numerical identifier associated with an interface participating in an IP network.

An IP address serves two related purposes:

1. It identifies an endpoint or interface.
2. Its network prefix provides information used by routers to determine where traffic belongs.

The address alone is not always sufficient to understand its routing behavior. The associated prefix length is equally important.

For example, `192.168.10.25/24` means:

- Address: `192.168.10.25`
- Prefix length: `/24`
- Network: `192.168.10.0/24`
- Network address: `192.168.10.0`
- Broadcast address: `192.168.10.255`
- Typical usable host range: `192.168.10.1` through `192.168.10.254`

The `/24` does not describe the individual address. It describes how many leading bits constitute the network prefix.

## IPv4

IPv4 uses 32 bits.

A conventional IPv4 address is written as four decimal octets separated by periods.

For example:

`192.168.10.25`

Each octet contains eight bits:

`192 . 168 . 10 . 25`

The total size is therefore:

`8 + 8 + 8 + 8 = 32 bits`

Each octet can contain a value from 0 through 255.

The Python implementation converts IPv4 addresses into integer and binary representations. The JavaScript and C++ implementations perform the same type of conversion explicitly.

### IPv4 binary representation

The decimal value `192` is represented as:

`11000000`

The decimal value `168` is:

`10101000`

Therefore:

`192.168.10.25`

can be represented as:

`11000000.10101000.00001010.00011001`

The binary representation becomes particularly important when subnet masks and CIDR prefixes are studied.

## IPv4 subnet masks

A subnet mask separates network bits from host bits.

For example:

`255.255.255.0`

has binary form:

`11111111.11111111.11111111.00000000`

The first 24 bits are network bits and the final eight bits are host bits.

This is equivalent to:

`/24`

A `/24` therefore contains:

`2^(32-24) = 256`

addresses.

In the traditional ordinary IPv4 subnet model, two addresses have special roles:

- The first address is the network address.
- The last address is the directed broadcast address.

Consequently, a normal `/24` has:

`256 - 2 = 254`

traditionally usable host addresses.

The special behavior of `/31` and `/32` means that the simple `total - 2` rule should not be applied blindly to every prefix.

## CIDR

CIDR stands for Classless Inter-Domain Routing.

CIDR represents an IPv4 or IPv6 network by writing an address followed by a slash and prefix length.

Examples:

- `10.0.0.0/8`
- `172.16.0.0/12`
- `192.168.1.0/24`
- `2001:db8:1234::/48`
- `2001:db8:1234:1::/64`

The prefix length specifies the number of leading bits belonging to the network prefix.

CIDR replaced older classful assumptions and allows networks to be divided into appropriately sized blocks.

## IPv4 subnetting

Subnetting divides a larger network into smaller networks.

Consider:

`192.168.1.0/24`

If it is divided into four equal `/26` networks, the resulting ranges are:

- `192.168.1.0/26`
- `192.168.1.64/26`
- `192.168.1.128/26`
- `192.168.1.192/26`

Each `/26` contains 64 addresses.

For ordinary IPv4 subnetting, each such subnet traditionally provides 62 usable host addresses.

The Python script demonstrates subnet calculations through `IPv4Network`. The JavaScript implementation calculates masks, network addresses, broadcast addresses, and host counts directly. The C++ implementation encapsulates these calculations in the `IPv4Network` class.

## Network address

The network address identifies the subnet itself.

For:

`192.168.10.25/24`

the network address is:

`192.168.10.0`

The calculation is conceptually equivalent to applying a bitwise AND between the IP address and subnet mask.

## Broadcast address

For ordinary IPv4 networks, the broadcast address contains all host bits set to one.

For:

`192.168.10.0/24`

the broadcast address is:

`192.168.10.255`

Broadcast behavior has important operational implications. IPv6 does not use broadcast addressing.

## Host address

A host address identifies an individual interface within a subnet.

For a traditional `/24`:

`192.168.10.1`

through:

`192.168.10.254`

are commonly used for hosts.

Actual deployment rules can reserve specific addresses for gateways, infrastructure, management, or other purposes.

## Public IPv4 addresses

A public IPv4 address is generally an address that can be globally routed on the public Internet, subject to routing policy and special-purpose allocations.

A globally routable address is not synonymous with an address that is reachable from every Internet host.

Firewalls, access-control lists, routing policy, security groups, and other controls can prevent inbound or outbound connectivity.

The Python classification example uses `ipaddress` properties to expose distinctions such as private and global status.

The JavaScript and C++ implementations use explicit known ranges for educational classification.

## Private IPv4 addresses

The three traditional RFC 1918 private IPv4 blocks are:

| Range | Prefix | Size |
|---|---:|---:|
| `10.0.0.0/8` | /8 | 16,777,216 addresses |
| `172.16.0.0/12` | /12 | 1,048,576 addresses |
| `192.168.0.0/16` | /16 | 65,536 addresses |

These ranges are widely used inside private networks.

Private IPv4 addresses are not globally routable as ordinary public Internet destinations.

Private addressing is common in:

- Home networks
- Corporate LANs
- Data centers
- Virtual networks
- Cloud private networks
- Laboratory environments
- Container and virtualization environments

A private address does not automatically mean that a host is trusted.

## Public versus private addressing

Public and private addressing solve different problems.

A private network can use an address such as:

`192.168.1.10`

A router can use NAT to translate that private endpoint into a public IPv4 endpoint.

The public endpoint may then communicate with external systems.

The distinction is important:

- Private addressing concerns address scope and intended use.
- Public addressing concerns global routability and allocation.
- NAT concerns translation between addressing domains.
- Firewall policy concerns whether traffic is permitted.

These are related concepts but should not be treated as synonyms.

## NAT

NAT stands for Network Address Translation.

A common IPv4 deployment pattern is:

`Private host -> NAT gateway -> Public IPv4 address -> Internet`

A simplified mapping might look like:

`192.168.1.10:50000 -> 203.0.113.10:40000`

The C++ and JavaScript programs simulate this relationship.

The Python implementation also contains a small NAT model.

The example is intentionally simplified. Production NAT behavior involves connection tracking, transport protocols, port allocation, timeout handling, filtering behavior, address pools, and many other considerations.

NAT is not an IP allocation protocol.

It is a translation mechanism.

## Special-purpose IPv4 addresses

Not every non-public IPv4 address is simply "private."

Several ranges have specialized meanings.

### Loopback

The IPv4 loopback block is:

`127.0.0.0/8`

The most familiar loopback address is:

`127.0.0.1`

Loopback traffic is directed back to the local host.

It is useful for:

- Local application testing
- Local services
- Development environments
- Host-only communication

### Link-local

The IPv4 link-local range is:

`169.254.0.0/16`

Link-local addresses are used for communication on a local link when normal configuration is unavailable or when link-local addressing is otherwise appropriate.

A link-local address should not be interpreted as an ordinary globally routed Internet address.

### Multicast

IPv4 multicast occupies:

`224.0.0.0/4`

Multicast addresses identify groups rather than one ordinary host destination.

Applications and protocols can use multicast for group communication.

### Limited broadcast

`255.255.255.255`

is the limited broadcast address.

Broadcast behavior is local to the relevant network context and is distinct from ordinary unicast addressing.

### Unspecified address

`0.0.0.0`

is the IPv4 unspecified address.

It can appear in contexts such as:

- A host that has not yet selected an address
- A server listening on all local IPv4 interfaces
- A default route written as `0.0.0.0/0`

Its meaning depends on context.

### Documentation networks

Common documentation ranges include:

- `192.0.2.0/24`
- `198.51.100.0/24`
- `203.0.113.0/24`

These are intended for documentation and examples.

The programs use them for demonstrations so that sample public-looking addresses do not need to represent real production services.

### Benchmarking

The IPv4 benchmarking range commonly used for network-device performance testing is:

`198.18.0.0/15`

It has a specialized purpose and should not be treated as an ordinary Internet destination range.

## Reserved versus special-purpose terminology

"Reserved" is often used informally to describe many addresses that have unusual behavior.

Technically, several different concepts should be distinguished:

- Private-use addresses
- Special-purpose addresses
- Documentation ranges
- Loopback addresses
- Link-local addresses
- Multicast addresses
- Unspecified addresses
- Reserved ranges
- Globally routed unicast addresses

The exact classification should be based on the relevant standards and registries rather than on a single generic "reserved" category.

## IPv4 address allocation

Address allocation is the process of assigning portions of an address space to networks, departments, sites, systems, or interfaces.

A common hierarchical structure is:

`Organization -> Site -> Network -> Subnet -> Host`

For example:

`10.100.0.0/16`

can be divided into smaller subnets for:

- Engineering
- Operations
- Security
- Servers
- Monitoring

The Python `IPv4AddressPlan`, JavaScript `IPv4Allocator`, and C++ `IPv4AddressPlan` classes demonstrate this idea.

A good address plan should consider:

- Current host requirements
- Future growth
- Network hierarchy
- Routing aggregation
- Security segmentation
- Geographic boundaries
- Organizational boundaries
- Infrastructure requirements
- Reserved capacity

## VLSM

VLSM stands for Variable Length Subnet Masking.

VLSM allows different subnets to have different sizes.

Suppose an organization has:

- Data Center: 60 hosts
- Engineering: 30 hosts
- Office: 14 hosts
- Management: 6 hosts

Giving every department a `/26` would waste significant address space.

VLSM allows each department to receive a subnet closer to its actual requirement.

The examples calculate suitable prefixes and allocate larger requirements first.

This ordering is a practical strategy because allocating large blocks first reduces the chance that small earlier allocations fragment the available address space.

## Address allocation and fragmentation

Address allocation must consider fragmentation.

Suppose a `/24` is available and several small subnets are allocated from it. A later request for a larger contiguous block might fail even though the total number of unused addresses is sufficient.

The addresses may be free but distributed across separate gaps.

This is why hierarchical planning and allocation order matter.

## Longest-prefix matching

Routers often use longest-prefix matching to choose among routes.

Consider:

- `0.0.0.0/0`
- `10.0.0.0/8`
- `10.20.0.0/16`
- `10.20.30.0/24`

For destination:

`10.20.30.99`

all four prefixes may match.

The most specific matching prefix is:

`10.20.30.0/24`

The C++ and JavaScript routing-table implementations explicitly demonstrate this process.

Longest-prefix matching is fundamental to hierarchical routing.

## Prefix aggregation

Multiple adjacent networks can sometimes be represented by a larger common prefix.

For example:

- `192.168.0.0/24`
- `192.168.1.0/24`
- `192.168.2.0/24`
- `192.168.3.0/24`

can be represented by:

`192.168.0.0/22`

when the address boundaries and alignment requirements permit aggregation.

The Python script uses `ipaddress.collapse_addresses` to demonstrate this.

Aggregation can reduce the number of routing-table entries.

It is important to distinguish aggregation from arbitrary merging. A larger prefix must accurately cover the desired address ranges without unintentionally including unrelated networks.

## IPv6

IPv6 uses 128-bit addresses.

An IPv6 address is commonly written as eight groups of four hexadecimal digits.

For example:

`2001:0db8:1234:5678:0000:0000:0000:0001`

The address can be compressed to:

`2001:db8:1234:5678::1`

IPv6's 128-bit address space is vastly larger than IPv4's 32-bit address space.

## IPv6 hexadecimal groups

Each IPv6 group contains 16 bits.

There are eight groups:

`8 × 16 = 128 bits`

For example:

`2001:db8:1234:5678::1`

contains a total of 128 bits even though several zero groups are represented by `::`.

## IPv6 zero compression

IPv6 permits consecutive zero groups to be compressed using `::`.

For example:

`2001:0db8:0000:0000:0000:0000:0000:0001`

can become:

`2001:db8::1`

Leading zeroes within individual groups can also be omitted.

For example:

`0db8`

becomes:

`db8`

A single `::` can represent one or more consecutive zero groups.

An address cannot contain multiple separate `::` sequences because that would make the expansion ambiguous.

The C++ implementation contains an explicit IPv6 parser and compression algorithm.

The JavaScript implementation similarly expands and normalizes IPv6 notation.

## IPv6 global unicast

Global unicast addresses are intended for global routing.

A commonly encountered example is:

`2001:4860:4860::8888`

The exact routing and allocation properties of an address depend on current registry and routing information.

The important conceptual distinction is that IPv6 has a large global unicast address space and does not require private IPv4-style scarcity management for ordinary addressing.

## IPv6 unique local addresses

IPv6 unique local addresses occupy:

`fc00::/7`

They are intended for local communication and are not ordinary globally routed Internet addresses.

A commonly used subset is formed under:

`fd00::/8`

Unique local addressing serves purposes similar to private IPv4 addressing, but the addressing architecture is different.

## IPv6 link-local addresses

IPv6 link-local addresses occupy:

`fe80::/10`

They are fundamental to IPv6 operation and are used for communication on a local link.

IPv6 nodes normally have link-local addressing on IPv6-enabled interfaces.

Link-local addresses are not ordinary globally routed addresses.

## IPv6 loopback

The IPv6 loopback address is:

`::1`

It is analogous in purpose to IPv4 `127.0.0.1`.

It represents the local host.

## IPv6 unspecified address

The IPv6 unspecified address is:

`::`

It is the all-zero IPv6 address.

Like `0.0.0.0` in IPv4, its meaning depends on context.

It is not an ordinary address assigned to a host interface for normal communication.

## IPv6 multicast

IPv6 multicast addresses begin with:

`ff00::/8`

IPv6 uses multicast instead of broadcast for functions requiring group-oriented delivery.

This is a significant conceptual difference between IPv4 and IPv6.

The C++ and JavaScript implementations detect multicast addresses by examining the high-order bits.

## IPv6 subnetting

A common IPv6 LAN prefix is:

`/64`

For example:

`2001:db8:1234:0010::/64`

A `/64` contains:

`2^64`

addresses.

The enormous size means that IPv6 subnet planning is fundamentally different from IPv4 host-count optimization.

A common hierarchical model is:

`/48 site prefix -> /64 LAN prefixes`

There are 16 bits between `/48` and `/64`.

Therefore:

`2^16 = 65,536`

possible `/64` subnets exist inside one `/48`.

The exact allocation provided by an ISP or registry can vary according to policy and organizational requirements.

## IPv6 prefix allocation

The Python and C++ examples model a `/48` site prefix:

`2001:db8:1234::/48`

and allocate `/64` prefixes such as:

- `2001:db8:1234:0::/64`
- `2001:db8:1234:1::/64`
- `2001:db8:1234:2::/64`
- `2001:db8:1234:3::/64`
- `2001:db8:1234:4::/64`

This demonstrates hierarchical allocation rather than the address scarcity calculations commonly associated with IPv4.

## SLAAC

SLAAC stands for Stateless Address Autoconfiguration.

IPv6 hosts can use Router Advertisements to learn information needed to configure addresses and routes.

A simplified conceptual model is:

`64-bit network prefix + 64-bit interface identifier`

The Python, JavaScript, and C++ programs demonstrate the mathematical construction of an IPv6 address from a `/64` prefix and a 64-bit identifier.

The demonstration is not a complete SLAAC implementation.

Actual IPv6 autoconfiguration involves Neighbor Discovery and Router Advertisement behavior.

Modern systems may use privacy-oriented interface identifiers instead of relying on a stable hardware-derived identifier.

## DHCPv6

DHCPv6 is another mechanism used in IPv6 networks for configuration.

SLAAC and DHCPv6 are not mutually exclusive in every deployment.

Different environments can use combinations of:

- Router Advertisements
- SLAAC
- DHCPv6
- Manually configured addresses
- Other network-management mechanisms

The choice depends on network architecture and operational requirements.

## IPv4 and IPv6 comparison

| Property | IPv4 | IPv6 |
|---|---|---|
| Address size | 32 bits | 128 bits |
| Common notation | Dotted decimal | Colon-separated hexadecimal |
| Example | `192.168.1.10` | `2001:db8::10` |
| Loopback | `127.0.0.1` | `::1` |
| Unspecified | `0.0.0.0` | `::` |
| Link-local | `169.254.0.0/16` | `fe80::/10` |
| Multicast | `224.0.0.0/4` | `ff00::/8` |
| Broadcast | Used | Not used |
| Private-style addressing | RFC 1918 | Unique Local Addresses |
| Common LAN prefix | Often `/24` | Often `/64` |
| NAT | Widely deployed | Not a fundamental requirement |

The table compares common addressing concepts. It does not imply that every deployment follows the same architecture.

## JavaScript-specific implementation

The JavaScript file intentionally avoids external packages.

### IPv4 arithmetic

JavaScript's bitwise operators operate on signed 32-bit integers. The implementation therefore uses unsigned conversion where appropriate.

The expression involving `>>> 0` converts the resulting bit pattern to an unsigned 32-bit value.

This matters when the most significant IPv4 bit is set.

The implementation also uses ordinary numeric arithmetic for several address calculations to avoid unnecessary complications from JavaScript's signed bitwise behavior.

### IPv4 CIDR calculations

`parseCIDR()`:

- Parses an address and prefix.
- Creates a subnet mask.
- Calculates the network address.
- Calculates the broadcast address.
- Calculates address capacity.
- Calculates a traditional usable-host count.

### IPv6 parser

`expandIPv6()` handles:

- Full eight-group notation.
- `::` compression.
- Leading zeroes.
- Hexadecimal validation.
- Group-count validation.

It intentionally does not implement every possible IPv6 textual variant, such as IPv4-embedded notation.

This is an important implementation-design decision: a teaching parser should explicitly define its supported input domain.

## Python implementation

The Python implementation uses the standard-library `ipaddress` module.

This library provides tested abstractions for:

- IPv4 addresses
- IPv6 addresses
- IPv4 networks
- IPv6 networks
- CIDR operations
- Network membership
- Subnet generation
- Address classification
- Address aggregation

Using a standard library is preferable to manually reproducing protocol arithmetic when the goal is application development rather than learning the underlying bit operations.

The Python implementation still includes explicit demonstrations so that the concepts remain visible.

### Python subnet calculations

`calculate_ipv4_subnet()` exposes:

- Network address
- Broadcast address
- Netmask
- Hostmask
- Prefix length
- Total addresses
- First usable address
- Last usable address
- Usable host count

### Python address classification

`classify_ipv4()` and `classify_ipv6()` expose standard-library address properties.

This is useful because production software should generally rely on well-tested parsing and address libraries rather than manually maintaining every special-purpose address rule.

### Python allocation model

`IPv4AddressPlan` provides a small address-plan manager.

It:

1. Receives a parent network.
2. Generates candidate child networks.
3. Checks overlap.
4. Allocates the first suitable free block.
5. Records the allocation.
6. Produces a report.

This demonstrates the basic structure of an address-management component.

## JavaScript implementation

The JavaScript implementation focuses on exposing the underlying mechanics.

It includes:

- `parseIPv4()`
- `ipv4ToInteger()`
- `integerToIPv4()`
- `ipv4ToBinary()`
- `prefixToMask()`
- `parseCIDR()`
- `classifyIPv4()`
- `IPv4Allocator`
- `RoutingTable`
- `NATSimulator`
- `expandIPv6()`
- `normalizeIPv6()`
- `classifyIPv6()`
- `IPv6PrefixAllocator`
- `NetworkInventory`

The file can run in a modern Node.js environment without an external package.

## C++ enterprise case study

The C++ program models a dual-stack enterprise network.

The scenario includes:

- An enterprise IPv4 address block
- Department-specific subnet allocation
- VLSM
- A routing table
- NAT
- An IPv6 site prefix
- IPv6 `/64` allocation
- Address classification
- Address-plan validation
- Dual-stack inventory
- Edge-case handling
- Assertions

This is substantially closer to the structure of a network-management component than isolated syntax demonstrations.

## C++ design approach

The program uses separate classes for different responsibilities.

### `IPv4Network`

This class models an IPv4 network and provides:

- CIDR parsing
- Network-address calculation
- Broadcast-address calculation
- Address capacity
- Usable-host calculation
- Address containment
- Network containment
- Overlap detection
- Subnet generation

Keeping these operations together creates a coherent abstraction for IPv4 networks.

### `IPv4AddressPlan`

This class manages multiple allocations inside a parent network.

Its main responsibility is allocation and reporting.

The design separates network arithmetic from allocation policy.

### `RoutingTable`

The routing table stores networks and next-hop descriptions.

The lookup operation scans matching routes and selects the route with the greatest prefix length.

For a small educational table this linear scan is straightforward.

Production routers use highly optimized data structures and specialized hardware or software techniques.

### `NATSimulator`

The NAT simulator maintains mappings from private endpoints to public endpoints.

An endpoint is represented by:

`IP address + transport port`

The port is necessary in this simplified model because many internal hosts can share the same public IP address.

Real NAT implementations have more complicated state and protocol behavior.

### `IPv6Address`

The C++ IPv6 class demonstrates:

- Parsing
- Zero expansion
- Zero compression
- Loopback detection
- Unspecified detection
- Link-local detection
- Multicast detection
- Unique-local detection
- Documentation-prefix detection
- Broad global-unicast classification

The parser deliberately handles the standard hexadecimal group structure rather than depending on an external library.

### `IPv6PrefixAllocator`

This class demonstrates how a `/48` can be divided into `/64` LAN prefixes.

The fourth 16-bit group is treated as the subnet identifier.

This reflects the structure of a common educational IPv6 address-planning model.

## Address validation

The implementations validate addresses before using them.

Validation prevents errors such as:

- IPv4 octets larger than 255
- Missing IPv4 octets
- Non-numeric IPv4 components
- Invalid IPv6 hexadecimal groups
- Too many IPv6 groups
- Invalid `::` placement
- Invalid prefix lengths
- Invalid port numbers
- Duplicate addresses
- Subnets outside their parent network
- Overlapping address allocations

Input validation is especially important in network-management software because invalid addressing data can propagate into routing, firewall, DHCP, inventory, and automation systems.

## Edge cases

### `/31` IPv4 networks

A `/31` contains two addresses.

Point-to-point IPv4 deployments can use `/31` addressing under appropriate operational standards.

Therefore, the traditional rule of subtracting two addresses does not apply in the same way.

The Python, JavaScript, and C++ examples explicitly recognize this distinction.

### `/32` IPv4 networks

A `/32` identifies one IPv4 address.

It is frequently used for:

- Host routes
- Router identifiers
- Loopback interfaces
- Policy entries
- Specific route destinations

### IPv6 `/128`

A `/128` identifies one IPv6 address.

It is the IPv6 equivalent of a single-address prefix.

### IPv6 `/127`

A `/127` contains two IPv6 addresses and is sometimes used for point-to-point infrastructure links.

The operational meaning of an IPv6 prefix depends on protocol and deployment context.

### IPv6 has no broadcast address

IPv6 does not use the IPv4 broadcast mechanism.

Multicast provides group-oriented communication.

This distinction affects protocol behavior and network design.

## Common mistakes

### Mistaking `172.16.0.0/12` for all `172.x.x.x`

Only the range:

`172.16.0.0/12`

is the RFC 1918 private block.

For example:

`172.20.1.1`

falls inside the private range.

But an arbitrary address such as:

`172.40.1.1`

does not fall inside that RFC 1918 block.

### Treating every non-public address as private

Private, link-local, loopback, multicast, documentation, and other special-purpose addresses have different meanings.

Classification should be precise.

### Assuming private means secure

A private address is not a security boundary.

A private host can be compromised, misconfigured, or reachable by other internal systems.

Security should use explicit controls such as authentication, authorization, segmentation, firewall rules, encryption, and monitoring.

### Assuming public means unsafe

A public address is not inherently malicious or insecure.

Public services can be securely operated through appropriate architecture and controls.

### Confusing NAT with a firewall

NAT translates addresses or ports.

A firewall applies traffic-control policy.

Some devices implement both, but they are conceptually different functions.

### Assuming IPv6 requires NAT

IPv6 was designed with a much larger address space and does not depend on NAT for address conservation in the way commonly experienced with IPv4.

NAT-like techniques can exist in IPv6 environments, but they are not the fundamental reason IPv6 provides large-scale addressing.

### Calculating IPv6 host capacity like IPv4

A `/64` contains:

`2^64`

addresses.

Trying to optimize IPv6 LAN prefixes around small host counts using traditional IPv4-style calculations is generally not the intended addressing model.

### Ignoring address hierarchy

An address plan that assigns arbitrary subnets without considering site, region, department, or routing boundaries can make route aggregation and management more difficult.

## Performance considerations

### Address parsing

Parsing an IPv4 address is effectively constant time because the representation contains exactly four octets.

IPv6 parsing also operates on a fixed maximum of eight 16-bit groups, making the basic parsing operation effectively constant time with respect to address size.

### Network membership

A CIDR membership test can be implemented using:

`address AND mask == network`

This requires a small fixed number of operations for IPv4.

The JavaScript and C++ examples expose this mechanism directly.

### Routing lookup

The educational `RoutingTable` implementation uses a linear search.

If there are `n` routes, a simple lookup can require checking up to `n` entries, giving:

`O(n)`

time complexity.

Real routing systems need much faster lookup techniques when route tables contain large numbers of entries.

### Allocation

The educational allocation algorithms search candidate subnets sequentially.

This is sufficient for demonstrating address planning but is not optimized for extremely large-scale IP address management.

Production IPAM systems can maintain indexes, free-space structures, allocation metadata, reservations, and transactional state.

### Aggregation

Prefix aggregation can reduce routing-table size.

A smaller routing table can improve lookup efficiency and reduce control-plane overhead, provided the aggregation accurately reflects reachable topology.

## Security considerations

IP address classification can be useful for security validation, but classification alone is not a complete security mechanism.

Examples of potentially important checks include:

- Rejecting unexpected loopback destinations in an externally supplied destination field.
- Detecting link-local addresses when they are not valid for an application.
- Handling multicast input explicitly.
- Validating whether private addresses are acceptable for a given interface.
- Preventing SSRF-style requests to unintended internal destinations.
- Enforcing network segmentation.
- Applying firewall policies independently of address classification.
- Logging address and prefix changes.
- Protecting address-management databases.
- Validating configuration before deploying routing changes.

A security system should not assume that a particular IP category automatically indicates trustworthiness.

## IP allocation considerations

A practical address plan should document:

- Parent address block
- Prefix length
- Site
- Region
- VLAN or segment
- Purpose
- Gateway
- Reserved addresses
- DHCP ranges
- Static allocations
- Infrastructure ranges
- Growth capacity
- Routing boundaries
- Security boundaries
- Ownership
- Allocation status

An address plan should also prevent overlapping networks.

The provided implementations demonstrate overlap detection and parent-network validation.

## Production considerations

A production IP address-management system requires considerably more than arithmetic.

Relevant concerns include:

- Persistent storage
- Concurrency control
- Transactions
- Authentication
- Authorization
- Audit logging
- Reservation management
- DHCP integration
- DNS integration
- Cloud integration
- IPv4 and IPv6 support
- Prefix delegation
- Multi-site hierarchy
- Conflict detection
- Import and export
- Monitoring
- API validation
- Backup and recovery

An educational allocator should therefore not be mistaken for a production IPAM platform.

## Important distinctions

| Concept | Meaning |
|---|---|
| IP address | Numerical address associated with an IP interface |
| Network prefix | Leading portion identifying a network |
| CIDR | Prefix-based notation such as `/24` or `/64` |
| Subnet mask | IPv4 bit mask separating network and host portions |
| Private address | Address intended for private-use scope |
| Public/global address | Address intended for global routing, subject to routing policy |
| Loopback | Address used for the local host |
| Link-local | Address intended for communication on a local link |
| Multicast | Address identifying a group |
| Unspecified | Special address representing absence of a normal assigned source/destination address |
| NAT | Translation between addressing/port domains |
| VLSM | Allocation of differently sized subnets |
| Prefix aggregation | Representing multiple compatible routes using a larger prefix |
| SLAAC | IPv6 stateless address autoconfiguration mechanism |
| Dual stack | Operating IPv4 and IPv6 together |

## Python, JavaScript, and C++ comparison

| Implementation | Primary emphasis |
|---|---|
| Python | Standard-library IP manipulation, classification, allocation, validation, testing |
| JavaScript | Explicit address arithmetic, CIDR calculations, IPv6 parsing, application-oriented simulation |
| C++ | Structured enterprise network case study, custom data structures, routing, allocation, validation |

Python is particularly concise for network-management scripts because the standard library provides an IP address abstraction.

JavaScript is useful when network-management logic needs to run in a web application or JavaScript-based service.

C++ is useful when explicit data structures, low-level representation, predictable resource behavior, or integration with systems software are important.

## Practical applications

IP addressing concepts appear in:

- Enterprise networks
- Internet service providers
- Cloud networking
- Data centers
- Virtual private clouds
- VPNs
- Firewalls
- Routers
- Switches
- Container platforms
- Kubernetes networking
- Service meshes
- Network monitoring
- Network automation
- DNS infrastructure
- DHCP infrastructure
- IP address management systems
- Security operations
- Network troubleshooting

## Debugging approach

When troubleshooting an IP-addressing problem, examine the configuration in layers.

### Address validity

Confirm that the address is syntactically valid.

### Address family

Determine whether the system is using IPv4, IPv6, or both.

### Prefix

Check the prefix length.

An address without its prefix can be misleading.

### Network membership

Determine whether source and destination belong to the expected subnet.

### Gateway

Check whether the next-hop gateway belongs to the correct network.

### Routing

Inspect the routing table and determine the longest matching prefix.

### NAT

If IPv4 NAT is involved, determine whether translation exists and whether the translated endpoint is correct.

### Firewall

Check whether security policy permits the traffic.

### DNS

Separate name-resolution problems from IP-connectivity problems.

### IPv6-specific behavior

Check:

- Link-local addressing
- Router Advertisements
- Neighbor Discovery
- Default routes
- Prefix configuration
- SLAAC
- DHCPv6 where applicable
- Multicast behavior

## Implementation limitations

The implementations are educational rather than complete protocol stacks.

The Python script relies on the standard `ipaddress` module for robust address operations.

The JavaScript IPv6 implementation intentionally supports the primary hexadecimal IPv6 forms needed by the study examples and does not attempt to implement every possible textual representation.

The NAT simulations model the conceptual mapping between private and public endpoints but do not implement real packet forwarding.

The C++ routing table uses a linear lookup rather than a production routing-table data structure.

The C++ IPv6 implementation models address representation and classification rather than implementing Neighbor Discovery, Router Advertisements, SLAAC messaging, or actual IPv6 packet transmission.

These limitations are deliberate because the objective is to demonstrate IP-addressing concepts and the architecture of useful software components.

## Program execution

### Python

The Python script can be executed with a modern Python 3 installation.

The program requires no third-party packages because it uses the standard `ipaddress` library.

It prints demonstrations for IPv4, IPv6, subnetting, classification, allocation, routing, NAT, validation, aggregation, and dual-stack inventory.

### JavaScript

The JavaScript file is designed for a modern JavaScript runtime such as Node.js.

It requires no external npm packages.

The program demonstrates IPv4 calculations directly and includes an educational IPv6 parser and prefix allocator.

### C++

The C++ program targets C++17 or later.

A typical compilation command is:

`g++ -std=c++17 -O2 -Wall -Wextra -pedantic ip_addressing_case_study.cpp -o ip_addressing_case_study`

The resulting executable runs the enterprise case study and its built-in assertions.

## Key formulas

### IPv4 total addresses

For prefix length `p`:

`2^(32-p)`

### Traditional IPv4 usable hosts

For ordinary IPv4 subnets where network and broadcast addresses are reserved:

`2^(32-p) - 2`

Special prefixes such as `/31` and `/32` require separate treatment.

### IPv6 total addresses

For prefix length `p`:

`2^(128-p)`

### IPv6 `/48` to `/64` subnet count

The difference is:

`64 - 48 = 16 bits`

Therefore:

`2^16 = 65,536`

possible `/64` prefixes exist inside a `/48`.

## Address-planning principles

A technically sound address plan should:

1. Use clearly defined hierarchical prefixes.
2. Avoid overlapping networks.
3. Allocate address space according to actual organizational boundaries.
4. Leave room for growth.
5. Consider route aggregation.
6. Separate infrastructure and user networks where appropriate.
7. Document reservations.
8. Treat IPv4 and IPv6 as distinct address families.
9. Validate configuration before deployment.
10. Avoid treating address categories as security decisions by themselves.

## Files and implementation correspondence

### Python implementation

The Python program contains:

- IPv4 fundamentals
- Binary representation
- CIDR calculations
- Subnetting
- Public/private classification
- Special-purpose ranges
- IPv4 allocation
- VLSM
- Longest-prefix routing
- NAT simulation
- IPv6 representation
- IPv6 classification
- IPv6 prefix allocation
- SLAAC-style address construction
- Validation
- Edge cases
- Aggregation
- Security-oriented checks
- Testing
- Dual-stack inventory

### JavaScript implementation

The JavaScript program contains:

- Direct IPv4 parsing
- IPv4 integer conversion
- Binary conversion
- CIDR mask calculations
- IPv4 classification
- IPv4 allocation
- VLSM
- Longest-prefix matching
- NAT mapping
- IPv6 expansion
- IPv6 normalization
- IPv6 classification
- IPv6 prefix allocation
- SLAAC-style construction
- Dual-stack inventory
- Validation and assertions

### C++ implementation

The C++ program contains:

- `IPv4Network`
- `IPv4AddressPlan`
- `IPv4Classification`
- VLSM allocation
- `RoutingTable`
- `NATSimulator`
- `IPv6Address`
- `IPv6PrefixAllocator`
- `NetworkInventory`
- Address-plan validation
- Edge-case processing
- Assertions
- A complete dual-stack enterprise case study

## Core technical relationships

The major concepts can be connected as follows:

An IP address belongs to an address family.

The address family determines the representation and address size.

A prefix defines the network boundary.

The network boundary determines subnet membership.

Subnetting divides a larger prefix into smaller prefixes.

Address allocation assigns those prefixes to organizational or technical purposes.

Routing uses prefixes to determine where packets should be forwarded.

Longest-prefix matching selects the most specific applicable route.

NAT can translate private IPv4 endpoints into public IPv4 endpoints.

IPv6 provides a much larger address space and uses hierarchical prefix allocation.

IPv6 multicast replaces the need for IPv4-style broadcast mechanisms.

Dual-stack networks operate IPv4 and IPv6 simultaneously, requiring independent addressing and routing considerations for each protocol family.
