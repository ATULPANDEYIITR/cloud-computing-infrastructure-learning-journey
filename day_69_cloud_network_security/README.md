# Cloud Network Security: Security Groups, Firewalls, Network ACLs and Traffic Filtering

## 1. Technical Scope

This project implements a cloud network security policy engine using five independent technical representations:

- Python: object-oriented network policy simulation and automated testing.
- JavaScript: event-driven security inspection and connection tracking.
- C++17: rule evaluation engine using structured domain models and STL containers.
- Java 17: enterprise network security service with immutable records, interfaces and policy abstractions.
- PostgreSQL: relational policy management, packet inspection, auditing and reporting.

The implementations use an IPv4 application network with a public-facing application server, a restricted administrative subnet, a private database subnet and a perimeter firewall.

The central objective is to determine whether a network packet satisfies every applicable security control.

## 2. Cloud Network Security Architecture

Cloud network security controls govern communication between workloads, subnets, virtual networks and external networks.

The implementation separates three policy mechanisms.

| Mechanism | Scope | Stateful | Rule behavior |
|---|---|---|---|
| Security group | Network interface or cloud resource | Yes | Allow rules |
| Network ACL | Subnet boundary | No | Ordered allow and deny rules |
| Firewall | Network perimeter or inspection point | Depends on implementation | Ordered allow and deny rules |

These mechanisms are complementary. A permitted connection at one layer does not automatically override a denial at another layer.

### 2.1 Security Groups

A security group is a virtual network control associated with a cloud resource or network interface.

Its principal characteristics are:

- Stateful connection handling.
- Inbound and outbound traffic rules.
- Allow-based rule configuration.
- Implicit denial of unmatched traffic.
- Automatic permission for return traffic belonging to an established connection.

Example application policy:

| Direction | Source or destination | Protocol | Port | Decision |
|---|---|---|---|---|
| Inbound | 0.0.0.0/0 | TCP | 443 | Allow |
| Inbound | 10.0.1.0/24 | TCP | 22 | Allow |
| Outbound | 10.0.2.0/24 | TCP | 5432 | Allow |
| Inbound | Other sources | Any | Any | Deny |

The HTTPS rule allows incoming application traffic. The administrative rule restricts SSH access to the management subnet. The database rule permits outbound PostgreSQL connectivity to a private subnet.

Security groups do not require a separate rule for return traffic when the connection is recognized as established.

### 2.2 Network ACLs

A Network Access Control List operates at subnet level.

Its defining characteristic is stateless filtering.

Every packet is evaluated independently. Permission for an inbound request does not automatically permit the corresponding outbound response.

Network ACLs generally support:

- Inbound rules.
- Outbound rules.
- Explicit allow decisions.
- Explicit deny decisions.
- Ordered rule evaluation.
- Default denial when no rule matches.

Example:

| Rule number | Direction | Source or destination | Port | Action |
|---|---|---|---|---|
| 100 | Inbound | 0.0.0.0/0 | 443 | Allow |
| 110 | Inbound | 10.0.1.0/24 | 22 | Allow |
| 100 | Outbound | 0.0.0.0/0 | All TCP ports | Allow |

The outbound policy is necessary for the stateless ACL to permit matching response traffic.

For production configurations, TCP ephemeral-port ranges must be considered when designing return traffic rules. The demonstration uses a broad outbound TCP range to keep the policy evaluation straightforward.

### 2.3 Firewalls

A firewall inspects traffic using configured security rules.

It may operate at different architectural levels:

- Network perimeter.
- Virtual network boundary.
- Subnet boundary.
- Host or workload boundary.
- Application layer.

The firewall implementation uses ordered first-match processing.

A firewall rule contains:

- Rule identifier.
- Direction.
- Action.
- Protocol.
- Source or destination CIDR.
- Port range.
- Priority.
- Description.

The lowest numerical priority is evaluated first.

Example:

| Priority | Source | Port | Action |
|---|---|---|---|
| 10 | 198.51.100.0/24 | Any | Deny |
| 100 | 0.0.0.0/0 | 443 | Allow |
| 110 | 10.0.1.0/24 | 22 | Allow |

A packet originating from the denied network is rejected before the HTTPS allow rule is considered.

This illustrates why firewall rule order is a security-critical configuration decision.

The example models a stateful firewall with connection tracking. Actual firewall behavior depends on the cloud provider, firewall product and selected inspection mode.

## 3. Network Traffic and Packet Filtering

A packet is represented by the following attributes:

| Attribute | Description |
|---|---|
| Source IP | Originating IPv4 address |
| Destination IP | Receiving IPv4 address |
| Protocol | TCP, UDP, ICMP or ALL |
| Source port | Originating transport port |
| Destination port | Receiving transport port |
| Direction | Inbound or outbound |

The evaluation engine compares packet attributes against network rules.

### 3.1 CIDR Notation

Classless Inter-Domain Routing represents IP address ranges using a network address and prefix length.

Examples:

| CIDR | Address capacity |
|---|---:|
| 10.0.0.0/8 | 16,777,216 |
| 10.0.1.0/24 | 256 |
| 10.0.1.0/28 | 16 |
| 192.168.1.0/24 | 256 |
| 0.0.0.0/0 | All IPv4 addresses |

The implementations validate IPv4 addresses and CIDR prefixes before evaluating network rules.

The C++ and Java implementations use integer representations of IPv4 addresses. JavaScript performs unsigned 32-bit address calculations. Python uses the standard `ipaddress` module.

The PostgreSQL implementation uses native `INET` and `CIDR` types.

### 3.2 Protocol Filtering

| Protocol | Typical application |
|---|---|
| TCP | HTTPS, SSH, PostgreSQL |
| UDP | DNS, selected application protocols |
| ICMP | Network diagnostics and error reporting |
| ALL | Any supported protocol |

TCP and UDP rules are evaluated using transport ports.

ICMP does not use TCP or UDP port numbers. Consequently, the implementations require zero packet ports for ICMP and unrestricted port fields for ALL protocol rules.

### 3.3 Port Filtering

Common application ports include:

| Port | Service |
|---:|---|
| 22 | SSH |
| 53 | DNS |
| 80 | HTTP |
| 443 | HTTPS |
| 5432 | PostgreSQL |
| 3306 | MySQL |
| 3389 | Remote Desktop |

Production security policies should expose only the ports required by the application architecture.

## 4. Combined Security Evaluation

The project evaluates traffic using the following sequence:

    Incoming or outgoing packet
                |
                v
         Packet validation
                |
                v
          Network ACL
                |
                v
         Security Group
                |
                v
             Firewall
                |
          +-----+-----+
          |           |
        ALLOW        DENY
          |           |
          v           v
      Application   Reject packet
       processing   and record audit

The evaluation terminates immediately when a layer denies traffic.

This prevents an allow rule in a later layer from overriding an earlier denial.

### 4.1 Example: Permitted HTTPS

Packet:

| Field | Value |
|---|---|
| Source | 203.0.113.10 |
| Destination | 10.0.0.10 |
| Protocol | TCP |
| Source port | 51000 |
| Destination port | 443 |
| Direction | Inbound |

Expected evaluation:

| Layer | Decision |
|---|---|
| Network ACL | Allow |
| Security group | Allow |
| Firewall | Allow |
| Final result | Allow |

### 4.2 Example: Blocked Hostile Source

Packet:

| Field | Value |
|---|---|
| Source | 198.51.100.20 |
| Destination | 10.0.0.10 |
| Protocol | TCP |
| Destination port | 443 |
| Direction | Inbound |

The packet satisfies the HTTPS network ACL and security group rules.

The firewall evaluates its higher-priority denial rule and blocks the packet.

Final result: Deny.

### 4.3 Example: Unauthorized SSH

A connection originating from 203.0.113.20 and targeting TCP port 22 is rejected.

The source does not belong to the permitted management network, 10.0.1.0/24.

The packet therefore fails the relevant inbound policy checks.

## 5. Stateful and Stateless Connection Handling

Connection tracking is an important distinction between the implemented security mechanisms.

### Stateful Filtering

A stateful security control maintains information about established connections.

A connection record includes:

- Source IP.
- Destination IP.
- Protocol.
- Source port.
- Destination port.
- Connection expiration.

When a packet matches an established connection in either direction, the security group can permit its return traffic without requiring an additional reverse-direction rule.

The Python, JavaScript, C++ and Java implementations model this using connection-tracking structures.

The JavaScript and Java implementations include expiration handling. The Python and C++ demonstrations retain connection entries for the lifetime of their respective simulator instances.

### Stateless Filtering

A stateless network ACL does not automatically recognize response traffic.

Both directions require explicit rules.

For example, an inbound HTTPS request can be allowed while its response is blocked if the outbound ACL does not permit the corresponding traffic.

This is a frequent source of connectivity failures in cloud network configurations.

### Connection Tracking Limitations

The implemented connection trackers are educational models.

They use simplified flow matching and do not implement complete TCP state machines, retransmission handling, sequence-number validation, NAT translation, fragment reassembly or distributed connection synchronization.

Production cloud security systems must handle these concerns through their actual networking infrastructure.

## 6. Python Implementation

The Python implementation models network security using dataclasses, enumerations and specialized policy classes.

### Core components

| Component | Responsibility |
|---|---|
| `Packet` | Validates packet attributes |
| `NetworkRule` | Defines matching conditions |
| `ConnectionTracker` | Maintains established flows |
| `SecurityGroup` | Evaluates stateful allow rules |
| `NetworkACL` | Evaluates stateless ordered rules |
| `Firewall` | Evaluates prioritized firewall policies |
| `CloudNetwork` | Coordinates policy evaluation |

### Important implementation decisions

- `ipaddress` provides reliable IPv4 and CIDR processing.
- Dataclasses represent immutable packet and rule definitions.
- Enumerations prevent inconsistent direction and action values.
- Sets provide efficient connection membership checks.
- Lists maintain rule collections.
- Assertions validate representative traffic scenarios.
- JSON export preserves the configured security policy.

The policy export writes a JSON representation to `cloud_security_policy.json`.

The script uses only Python standard-library modules.

## 7. JavaScript Implementation

The JavaScript implementation emphasizes event-driven policy evaluation and asynchronous inspection.

### Core components

- `Rule`: validates and freezes individual policy definitions.
- `PolicyLayer`: provides shared ordered-rule functionality.
- `SecurityGroup`: implements stateful allow decisions.
- `NetworkACL`: implements stateless filtering.
- `Firewall`: evaluates prioritized rules and connection state.
- `CloudNetworkEngine`: coordinates packet inspection.

### Event-driven behavior

The engine emits three important events:

| Event | Meaning |
|---|---|
| `inspection` | A policy layer has evaluated traffic |
| `allowed` | Every configured layer permitted traffic |
| `denied` | A policy layer rejected traffic |

The inspection method is asynchronous and processes policy layers sequentially.

This design makes the engine suitable for extension with asynchronous policy sources, external audit services and event consumers.

Node.js built-in modules provide:

- `net` for IP address validation.
- `fs/promises` for asynchronous policy export.
- `events` for event-driven behavior.

The JavaScript connection tracker uses a `Map` and an expiration timestamp.

## 8. C++17 Implementation

The C++ implementation focuses on efficient domain modeling and predictable rule evaluation.

### Core components

| Component | Responsibility |
|---|---|
| `CIDR` | IPv4 subnet representation |
| `Packet` | Network packet representation |
| `Rule` | Policy matching |
| `ConnectionTracker` | Established connection storage |
| `SecurityGroup` | Stateful access evaluation |
| `NetworkACL` | Stateless filtering |
| `Firewall` | Priority-based evaluation |
| `CloudSecurityEngine` | Multi-layer policy enforcement |

The implementation uses:

- `enum class` for strongly typed security states.
- `struct` for packet and evaluation records.
- `vector` for ordered policy collections.
- `set` for established connection lookup.
- `tuple` for connection keys.
- STL algorithms for rule validation and sorting.
- Exceptions for invalid network configurations.

### Performance characteristics

For a policy layer containing R rules, a sequential rule search has O(R) worst-case evaluation time.

Sorting firewall or ACL rules during configuration takes O(R log R).

Connection membership checks using an ordered set take O(log C), where C is the number of tracked connections.

A production implementation could introduce prefix-based indexes, protocol-specific rule indexes and hash-based flow tracking to reduce lookup costs.

## 9. Java 17 Implementation

The Java implementation emphasizes enterprise service boundaries, typed domain objects and reusable policy abstractions.

### Domain model

Records represent immutable values:

- `IPv4`
- `CIDR`
- `Packet`
- `Rule`
- `ConnectionKey`
- `Evaluation`

The `PolicyLayer` interface defines the inspection contract.

`AbstractPolicyLayer` centralizes rule registration, duplicate detection and ordered evaluation.

Specialized classes implement different security semantics without duplicating the common rule-matching mechanism.

### Enterprise engineering decisions

- Immutable records reduce accidental modification of packet and rule data.
- Enums constrain supported policy states.
- `LinkedHashMap` provides deterministic rule registration.
- Streams support ordered policy retrieval.
- Custom exceptions distinguish policy validation failures.
- Synchronized connection-tracking methods protect shared state within the JVM.
- The service class coordinates independent security controls.

The implementation demonstrates separation between packet representation, policy definition, connection tracking and security evaluation.

## 10. PostgreSQL Implementation

The PostgreSQL implementation models a relational cloud security management system.

### Database relationships

    Cloud Accounts
          |
          v
    Network Resources
          |
          +---------------------+
          |                     |
          v                     v
    Security Groups        Network ACLs
          |                     |
          v                     v
    Security Group Rules   ACL Rules

    Cloud Accounts
          |
          v
       Firewalls
          |
          v
     Firewall Rules

    Network Resources
          |
          v
    Packet Inspections
          |
          v
     Inspection Audit

    Network Resources
          |
          v
    Tracked Connections

### Principal tables

| Table | Purpose |
|---|---|
| `cloud_accounts` | Cloud account information |
| `network_resources` | Virtual network resources |
| `security_groups` | Stateful resource policies |
| `security_group_rules` | Security group permissions |
| `network_acls` | Subnet-level ACL definitions |
| `network_acl_rules` | Ordered stateless rules |
| `firewalls` | Firewall configurations |
| `firewall_rules` | Prioritized firewall rules |
| `packet_inspections` | Packet evaluation results |
| `inspection_audit` | Per-layer evaluation history |
| `tracked_connections` | Connection state and expiration |

### Data integrity

The schema uses:

- Primary keys for entity identification.
- Foreign keys for relational integrity.
- Unique constraints for rule identifiers and names.
- Check constraints for valid ports and configuration values.
- Enumerated types for controlled security states.
- Triggers for reusable rule validation.
- Indexes for frequent policy and audit queries.

PostgreSQL native `INET` and `CIDR` types provide network address storage and subnet comparison.

### Functions and procedures

`network_rule_matches()` centralizes CIDR, protocol, direction and port matching.

`evaluate_security_group()` evaluates resource-level stateful allow rules.

`evaluate_network_acl()` implements first-match stateless filtering.

`evaluate_firewall()` performs priority-based firewall evaluation.

`inspect_packet()` coordinates the complete security workflow and records each policy decision.

`expire_connections()` processes expired connection records.

### Reporting and analysis

The `network_security_summary` view provides resource-level traffic statistics.

The included queries identify:

- Allowed and denied packet counts.
- Rejected source addresses.
- Publicly exposed administrative ports.
- Rule counts by security layer.
- Packet inspection history.
- Connection expiration.
- Policy evaluation details.

The transaction example demonstrates how to disable a rule and roll back the change without permanently modifying demonstration data.

## 11. Rule Validation and Failure Conditions

The implementations reject invalid configurations before applying them.

| Condition | Expected behavior |
|---|---|
| Invalid IPv4 address | Reject |
| Invalid CIDR prefix | Reject |
| Port below zero | Reject |
| Port above 65535 | Reject |
| Starting port greater than ending port | Reject |
| Duplicate rule identifier | Reject |
| Negative firewall priority | Reject |
| Unsupported direction | Reject |
| Unsupported protocol | Reject |
| ICMP packet with nonzero ports | Reject |
| Unmatched security group packet | Deny |
| Unmatched ACL packet | Deny |
| Unmatched firewall packet | Deny |
| Firewall deny rule matches first | Deny |

A denied packet must not continue to application processing.

The PostgreSQL implementation additionally protects relational consistency through database constraints and transactional inspection records.

## 12. Security Design Considerations

### Least Privilege

Only required source networks, destination networks, protocols and ports should be permitted.

A public HTTPS endpoint does not justify unrestricted SSH or database access.

### Administrative Access

SSH should be restricted to controlled management networks.

Production environments should also consider identity-aware access, privileged access management, key-based authentication and administrative network isolation.

### Public Exposure

The CIDR `0.0.0.0/0` represents every IPv4 source address.

Rules using this range should be reviewed carefully, especially when they permit administrative or database ports.

### Default Deny

Unmatched traffic is denied.

This prevents unknown traffic from being implicitly permitted.

### Rule Ordering

Explicit firewall denial rules should appear before broader allow rules when the intended policy requires them to take precedence.

### Logging and Monitoring

Inspection records should capture:

- Packet source.
- Packet destination.
- Protocol.
- Port.
- Direction.
- Policy layer.
- Matching rule.
- Final decision.
- Timestamp.
- Rejection reason.

Production systems should use centralized log collection, retention policies, alerting and access controls.

### Network Segmentation

Application servers, databases, management interfaces and public endpoints should occupy appropriately separated network segments.

The example uses:

- 10.0.0.0/24 for the application subnet.
- 10.0.1.0/24 for administrative access.
- 10.0.2.0/24 for private database connectivity.

### IPv6 Considerations

The implementations intentionally focus on IPv4.

Production environments must independently configure IPv6 policies. IPv4-only controls do not automatically protect IPv6 traffic.

## 13. Implementation Comparison

| Capability | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| IPv4 validation | Yes | Yes | Yes | Yes | Native |
| CIDR matching | Yes | Yes | Yes | Yes | Native |
| Security groups | Yes | Yes | Yes | Yes | Yes |
| Network ACLs | Yes | Yes | Yes | Yes | Yes |
| Firewall policies | Yes | Yes | Yes | Yes | Yes |
| Connection tracking | Set | Map | Set | Map | Table |
| Rule priority | Yes | Yes | Yes | Yes | Yes |
| Policy audit | Yes | Yes | Yes | Yes | Yes |
| Persistent policy storage | JSON | JSON | Runtime | Runtime | Relational |
| Event-driven inspection | No | Yes | No | No | No |
| Database reporting | No | No | No | No | Yes |

## 14. Important Limitations

These implementations are policy simulators and management examples. They do not configure actual cloud infrastructure or intercept operating-system network packets.

Several production networking capabilities are deliberately outside their scope:

- IPv6 processing.
- TCP connection-state validation.
- UDP timeout semantics beyond simplified tracking.
- ICMP type and code filtering.
- Network Address Translation.
- Dynamic routing and route-table evaluation.
- Fragmented packet handling.
- Deep packet inspection.
- TLS inspection.
- Distributed firewall state synchronization.
- Cloud-provider-specific security group references.
- Managed firewall threat intelligence.
- Denial-of-service mitigation.
- Real-time enforcement across distributed network interfaces.

The connection-tracking examples also use simplified reverse-flow matching. They should not be treated as substitutes for production firewall connection-state engines.

The implementations establish the core policy concepts, validation mechanisms, rule ordering, stateful behavior, stateless filtering and audit workflows required to understand cloud network security.
