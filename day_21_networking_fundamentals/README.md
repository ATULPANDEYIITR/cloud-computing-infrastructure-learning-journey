# Networking Fundamentals and Wireshark Concepts

## Topic scope

This project develops a practical understanding of computer networking from fundamental concepts through packet-level analysis.

The implementations cover networks, hosts, clients, servers, packets, frames, protocols, ports, sockets, IP addressing, MAC addressing, subnetting, TCP, UDP, DNS, ARP, ICMP, routing, switching, NAT, firewalls, HTTP, HTTPS, packet capture concepts, Wireshark-style filtering, TCP conversations, traffic statistics, latency, packet loss, MTU, checksums, and network troubleshooting.

The three implementations deliberately approach the subject differently:

- Python provides a broad educational networking laboratory with reusable classes, packet models, simulations, validation, filtering, routing, and analysis.
- JavaScript demonstrates the same networking concepts using classes, collections, asynchronous DNS behavior, Node.js networking APIs, buffers, and application-level parsing.
- C++ models an industry-style network monitoring and troubleshooting system with strongly typed structures, routing, firewall policy, NAT, packet analysis, TCP stream grouping, and self-tests.

No external package is required by any implementation.

## Fundamental networking concepts

### What is a computer network?

A computer network is a system in which devices exchange information using communication technologies and agreed protocols.

A network can be extremely small, such as two directly connected computers, or extremely large, such as the global Internet.

A network normally contains several categories of components:

- End devices such as laptops, phones, servers, printers, sensors, and virtual machines.
- Network interfaces that connect devices to networks.
- Switches that forward local link-layer traffic.
- Routers that forward traffic between IP networks.
- Wireless access points that provide wireless connectivity.
- Firewalls that enforce traffic policies.
- Servers that provide applications or infrastructure services.
- Clients that request services.

The word network therefore describes both the connected devices and the communication system that allows them to exchange information.

## Clients and servers

A client is a system or application that requests a service.

A server is a system or application that provides a service.

The distinction is based on the communication role rather than necessarily on the physical hardware.

A laptop can act as a client when accessing a web server and later act as a server when running a development web application.

A typical web interaction can be represented as:

`Client -> DNS -> destination address -> TCP/QUIC connection -> HTTP request -> HTTP response`

The roles are determined by the communication being performed.

## Hosts

A host is a network-connected device that can send or receive network traffic.

Examples include:

- Desktop computers
- Laptops
- Smartphones
- Servers
- Virtual machines
- Cloud instances
- Network appliances
- Internet-connected embedded systems

A host can have one or multiple network interfaces and can participate in multiple networks.

## Network interface

A network interface provides the connection between a device and a network.

A physical Ethernet adapter and a wireless adapter are examples of network interfaces.

Virtual machines and containers can also have virtual network interfaces.

A network interface commonly has a link-layer address such as a MAC address and can be configured with one or more IP addresses.

## Packets, frames, segments, and datagrams

These terms describe data at different protocol layers.

### Frame

A frame is a link-layer data unit.

An Ethernet frame commonly contains:

- Destination MAC address
- Source MAC address
- EtherType or related protocol identification
- Payload
- Error-detection information

The payload can contain an IP packet.

### Packet

A packet is commonly used for a network-layer unit such as an IP packet.

An IPv4 packet contains information such as:

- Source IP address
- Destination IP address
- Protocol identifier
- Time to Live
- Total length
- Identification and fragmentation information
- Header checksum

### Segment

A TCP data unit is commonly called a segment.

TCP provides information such as:

- Source port
- Destination port
- Sequence number
- Acknowledgement number
- Flags
- Window information
- Payload

### Datagram

UDP provides a datagram-oriented transport service.

A UDP datagram contains:

- Source port
- Destination port
- Length
- Checksum
- Application payload

The terminology is useful because it identifies the protocol layer being discussed.

## Encapsulation

Networking protocols normally use encapsulation.

An application creates data. A transport protocol adds transport information. IP adds network-layer information. Ethernet or another link protocol then carries the resulting packet.

Conceptually:

`Application data -> TCP segment -> IP packet -> Ethernet frame`

At the destination, the reverse process occurs:

`Ethernet frame -> IP packet -> TCP segment -> application data`

The Python, JavaScript, and C++ implementations all model this relationship.

## Protocols

A protocol is a set of rules that defines how systems communicate.

Protocols specify things such as:

- Message formats
- Field meanings
- Valid states
- Error handling
- Ordering
- Timing
- Addressing
- Negotiation
- Security mechanisms

Examples include:

| Protocol | Primary role |
|---|---|
| Ethernet | Local link communication |
| ARP | IPv4 address to MAC resolution |
| IP | Logical addressing and packet forwarding |
| ICMP | Network control and diagnostic messages |
| TCP | Reliable ordered byte-stream transport |
| UDP | Connectionless datagram transport |
| DNS | Name resolution |
| DHCP | Automatic network configuration |
| HTTP | Web application protocol |
| HTTPS | HTTP protected using TLS |
| SSH | Secure remote access |

## MAC addresses

A MAC address is a link-layer identifier used by technologies such as Ethernet.

A common Ethernet MAC address is represented as six hexadecimal bytes:

`00:11:22:33:44:55`

The Python and C++ implementations validate and normalize MAC addresses.

A MAC address is not the same thing as an IP address.

A simplified distinction is:

- MAC address: local link-layer addressing
- IP address: logical network-layer addressing

Switches primarily use MAC addresses when deciding where to forward Ethernet frames.

Routers primarily use IP addresses when deciding how to forward packets between networks.

## IP addresses

IPv4 addresses contain 32 bits.

They are normally written as four decimal octets:

`192.168.1.25`

Each octet ranges from 0 through 255.

IPv6 uses 128-bit addresses and has a substantially different textual representation and addressing model.

The Python implementation uses the standard `ipaddress` module for IPv4 validation and subnet calculations.

The JavaScript and C++ implementations implement IPv4 conversion and CIDR calculations directly.

## Private IPv4 address space

Common private IPv4 ranges include:

- `10.0.0.0/8`
- `172.16.0.0/12`
- `192.168.0.0/16`

Private addresses are commonly used inside local networks and are not directly routed across the public Internet in the same way as globally assigned addresses.

A private address often communicates with external systems through NAT.

## Loopback

The IPv4 loopback range includes `127.0.0.0/8`.

The address most commonly encountered is:

`127.0.0.1`

It refers to the local host rather than another physical computer.

The Python implementation also demonstrates a real system DNS lookup for `localhost`.

## CIDR notation

CIDR stands for Classless Inter-Domain Routing.

A network can be represented as:

`192.168.1.0/24`

The `/24` indicates that the first 24 bits form the network prefix.

The remaining 8 bits can represent addresses within that network.

A `/24` IPv4 network contains 256 total addresses.

Traditional IPv4 host-address conventions commonly leave the network address and broadcast address unavailable for ordinary host assignment, resulting in 254 commonly usable host addresses for a normal `/24` subnet.

## Subnet masks

The `/24` prefix corresponds to:

`255.255.255.0`

A `/16` corresponds to:

`255.255.0.0`

A `/26` corresponds to:

`255.255.255.192`

Subnetting divides an address space into smaller networks.

The Python, JavaScript, and C++ implementations calculate network membership and routing decisions using CIDR prefixes.

## Ports

A port identifies a transport-layer endpoint associated with a service or application.

TCP and UDP each have their own port spaces.

Ports range from:

`0` through `65535`

A commonly used classification is:

- `0-1023`: well-known ports
- `1024-49151`: registered ports
- `49152-65535`: dynamic/private ports

The exact allocation and operational use of ports is more nuanced than the simplified classification, but the ranges provide a useful conceptual model.

Examples include:

| Port | Common association |
|---:|---|
| 22 | SSH |
| 53 | DNS |
| 80 | HTTP |
| 123 | NTP |
| 443 | HTTPS |
| 3389 | RDP |

A client commonly uses a temporary source port when connecting to a server's listening port.

For example:

`192.168.1.25:53142 -> 93.184.216.34:443`

This identifies the two transport endpoints.

## Sockets

A socket is a software communication endpoint.

A TCP connection can be identified using a combination of:

- Source IP
- Source port
- Destination IP
- Destination port
- Transport protocol

The Python and JavaScript implementations demonstrate socket endpoint concepts, while the JavaScript implementation also uses Node.js's built-in `net` module.

## TCP

TCP is a connection-oriented transport protocol.

Important TCP properties include:

- Ordered delivery
- Sequence numbers
- Acknowledgements
- Retransmission mechanisms
- Flow control
- Connection state
- Congestion-control mechanisms

TCP does not simply mean that every application request is transmitted as one packet. Application data is treated as a byte stream and may be divided across multiple segments.

## TCP three-way handshake

A basic TCP connection begins with:

`Client -> Server: SYN`

`Server -> Client: SYN + ACK`

`Client -> Server: ACK`

The first segment communicates the client's initial sequence information.

The second segment acknowledges the client and provides the server's own sequence information.

The third segment acknowledges the server.

A packet analyzer can identify this sequence through TCP flags, sequence numbers, acknowledgement numbers, and timestamps.

The Python, JavaScript, and C++ implementations explicitly construct this handshake.

## TCP flags

Important TCP flags include:

| Flag | Meaning |
|---|---|
| SYN | Synchronization and connection establishment |
| ACK | Acknowledgement field is meaningful |
| FIN | Sender is finishing its side of the connection |
| RST | Reset or immediate termination |
| PSH | Push indication |
| URG | Urgent-data indication |

A Wireshark analysis frequently examines SYN, ACK, FIN, and RST behavior.

For example, a large number of SYN packets without corresponding SYN-ACK responses may indicate connectivity, filtering, routing, server availability, or other problems. The packet pattern alone does not prove a specific cause.

## TCP sequence numbers

TCP uses sequence numbers to track the byte stream.

If a segment carries 5 bytes beginning at sequence number `1001`, the next expected sequence position is generally:

`1006`

An acknowledgement indicates the next sequence number the receiver expects.

This allows packet analyzers to reason about ordering and missing data.

## TCP retransmissions

When TCP determines that data has not been successfully acknowledged, it can retransmit data.

A packet capture may contain indications of retransmission.

Retransmissions can be associated with:

- Packet loss
- Congestion
- Network problems
- Wireless interference
- Receiver behavior
- Path problems

Retransmission does not automatically prove that the network is physically broken. Packet-level evidence must be interpreted together with timing and other observations.

## TCP reset

A TCP RST indicates that a connection or segment is being rejected or reset.

Potential causes include:

- No service listening on the destination port
- Application-level termination
- Firewall behavior
- Operating-system behavior
- Protocol errors

A RST is evidence of a reset, not proof of the exact reason.

## UDP

UDP is a connectionless transport protocol.

It provides datagrams rather than a reliable ordered byte stream.

UDP does not provide TCP-style transport-layer connection establishment.

Applications using UDP may implement their own:

- Reliability
- Sequencing
- Retransmission
- Authentication
- Encryption
- Congestion behavior

DNS is a familiar example of a protocol that traditionally uses UDP for many queries, although DNS can also use TCP and other transport mechanisms.

## TCP and UDP comparison

| Property | TCP | UDP |
|---|---|---|
| Connection-oriented | Yes | No |
| Ordered byte stream | Yes | No |
| Transport acknowledgements | Yes | No |
| Automatic retransmission | Yes | No |
| Datagram boundaries | Not preserved | Preserved |
| Typical overhead | Higher | Lower |
| Common uses | Web, SSH, database connections | DNS, streaming, real-time applications |

The comparison should not be interpreted as TCP being universally superior to UDP. Applications select the transport characteristics appropriate to their requirements.

## DNS

DNS stands for Domain Name System.

DNS maps names to information such as IP addresses.

For example:

`example.test -> 192.0.2.10`

An actual DNS exchange can contain:

- Client source address
- DNS server destination address
- UDP or TCP ports
- Query name
- Query type
- Response records
- Response codes

The Python and JavaScript implementations include simulated DNS databases and a real local DNS lookup using standard runtime functionality.

The JavaScript implementation uses Node.js's asynchronous DNS API to demonstrate event-driven behavior.

## DNS failure

A DNS failure can occur even when the network itself is operational.

Possible causes include:

- Incorrect DNS server configuration
- DNS server unavailable
- Network path failure to the DNS server
- Incorrect DNS records
- Application-specific resolution behavior
- Local caching problems

Packet analysis can distinguish DNS traffic from subsequent application traffic.

## ARP

ARP stands for Address Resolution Protocol.

In traditional IPv4 Ethernet networks, ARP helps a host discover the MAC address associated with a local IPv4 address.

A simplified sequence is:

`Who has 192.168.1.1?`

followed by a response identifying the corresponding MAC address.

ARP operates on the local network segment.

IPv6 does not use ARP. IPv6 uses Neighbor Discovery mechanisms.

The Python, JavaScript, and C++ implementations model ARP information using simplified caches.

## ICMP

ICMP is used for network control and diagnostic messages.

Common ICMP messages include:

- Echo Request
- Echo Reply
- Destination Unreachable
- Time Exceeded

The `ping` utility commonly uses ICMP Echo Request and Echo Reply for IPv4.

Traceroute-style mechanisms can make use of Time Exceeded messages.

ICMP is not simply a "ping protocol." It serves several network-control purposes.

## DHCP

DHCP provides automatic network configuration.

A client may obtain information such as:

- IP address
- Subnet mask
- Default gateway
- DNS servers
- Lease information

A common conceptual DHCP exchange is represented by:

`Discover -> Offer -> Request -> Acknowledgement`

DHCP normally uses UDP.

## Ethernet

Ethernet is a common local-area networking technology.

Ethernet frames contain link-layer addressing and a payload.

A simplified Ethernet frame can be represented as:

`Destination MAC | Source MAC | EtherType | Payload`

The payload may contain an IPv4 packet.

Switches examine Ethernet frame information to decide where frames should be forwarded.

## Switches

A switch connects devices within a local network.

A managed Ethernet switch maintains information that associates MAC addresses with ports.

If a switch knows that a destination MAC address is reachable through a particular port, it can forward the frame toward that port.

A switch and router operate at different conceptual layers, although modern network devices can combine many functions.

## Routers

A router forwards IP packets between networks.

A router generally examines the destination IP address and consults a routing table.

A simplified routing table might contain:

| Destination | Next hop | Interface |
|---|---|---|
| `192.168.1.0/24` | Direct | LAN |
| `10.0.0.0/8` | `10.10.10.1` | WAN1 |
| `0.0.0.0/0` | `192.168.1.1` | LAN |

## Longest-prefix matching

Suppose a routing table contains:

`192.168.1.0/24`

and:

`0.0.0.0/0`

A destination such as `192.168.1.25` matches both routes.

The `/24` route is more specific than `/0`, so it is selected.

This is known as longest-prefix matching.

The C++ case study implements this explicitly.

## Default route

A default IPv4 route is commonly represented as:

`0.0.0.0/0`

It matches destinations not covered by more specific routes.

A host commonly sends Internet-bound traffic to its default gateway.

## NAT

NAT stands for Network Address Translation.

A common use is allowing private hosts to share a public address.

For example:

`192.168.1.25:53142`

may be translated to:

`203.0.113.20:42001`

before traffic is sent to an external destination.

NAT can maintain mappings containing:

- Internal address
- Internal port
- Translated address
- Translated port
- Destination
- Transport protocol

The Python, JavaScript, and C++ implementations model such mappings.

NAT is not the same thing as a firewall, although NAT devices frequently perform firewall functions as well.

## Firewalls

A firewall applies traffic policy.

A simple rule can contain:

- Source network
- Destination port
- Protocol
- Action
- Description

For example:

`192.168.1.0/24 + TCP + port 443 -> ALLOW`

A second rule might be:

`192.168.1.0/24 + TCP + port 22 -> DENY`

The examples use an implicit deny when no rule matches.

Real firewalls can inspect substantially more information, maintain connection state, apply identity policies, inspect applications, perform NAT, and integrate with security monitoring.

## Stateful versus stateless filtering

A stateless firewall evaluates packets according to rules without maintaining the full state of a connection.

A stateful firewall tracks connection state.

For TCP, stateful inspection can distinguish traffic belonging to established connections from unexpected traffic.

This allows more precise policy decisions than simple independent packet matching.

## Packet captures

A packet capture is a record of observed network traffic.

Depending on the capture environment, it may contain:

- Timestamp
- Frame size
- MAC addresses
- IP addresses
- Transport protocol
- Ports
- Protocol fields
- Application metadata
- Application payloads when visible

A capture does not necessarily contain every packet that exists on the network.

The capture location matters.

A capture taken on a host's network interface differs from a capture taken on a router, switch monitoring port, wireless capture interface, or other observation point.

## Wireshark

Wireshark is a packet-analysis application that can decode and display network protocols.

Its packet-analysis interface commonly allows an analyst to inspect:

- Packet list
- Packet details
- Raw packet bytes
- Protocol fields
- Timestamps
- Conversations
- Endpoints
- Protocol statistics
- TCP streams
- Display-filter results

The implementations in this project reproduce selected analytical concepts rather than implementing a complete packet-capture engine.

## Packet list

A packet list commonly contains fields such as:

- Packet number
- Time
- Source
- Destination
- Protocol
- Length
- Information

The Python, JavaScript, and C++ packet models implement similar fields.

The packet number is an identifier within the capture.

The timestamp is essential when analyzing latency, ordering, bursts, retransmissions, and application response time.

## Packet details

A packet analyzer can decode a packet into protocol layers.

A simplified packet might be shown conceptually as:

`Ethernet II`

containing:

`Internet Protocol`

containing:

`Transmission Control Protocol`

containing:

`HTTP`

Each layer exposes fields relevant to that protocol.

This layered view is one of the most useful features of packet analysis.

## Raw packet bytes

Packet analyzers can also show the underlying bytes.

Hexadecimal representations allow an analyst to connect decoded protocol fields with the bytes that actually appeared on the wire.

The Python implementation demonstrates binary conversion and IPv4 header construction.

The C++ implementation demonstrates a simplified Internet checksum calculation.

## Capture filters versus display filters

This distinction is important.

A capture filter restricts traffic at capture time.

A display filter restricts what is shown after packets have been captured.

A capture filter can reduce storage and processing requirements.

A display filter is generally more flexible during investigation because the underlying capture remains available.

Using an excessively restrictive capture filter can permanently remove evidence needed later.

## Wireshark display-filter examples

Common examples include:

`tcp`

Displays TCP traffic.

`udp`

Displays UDP traffic.

`dns`

Displays DNS traffic.

`http`

Displays traffic recognized as HTTP.

`icmp`

Displays ICMP traffic.

`ip.addr == 192.168.1.25`

Matches packets where the address is used as either endpoint.

`ip.src == 192.168.1.25`

Matches packets originating from the specified address.

`ip.dst == 8.8.8.8`

Matches packets sent to the specified destination.

`tcp.port == 443`

Matches TCP traffic involving port 443.

`tcp.flags.syn == 1`

Matches TCP packets with SYN set.

`tcp.flags.reset == 1`

Matches TCP reset packets.

`tcp.stream == 0`

Selects a TCP conversation associated with a stream identifier.

These examples are concepts demonstrated by the filtering systems in the project. The Python implementation includes a deliberately simplified filter parser.

## Filtering

Filtering is essential because real packet captures can contain thousands or millions of packets.

An analyst usually narrows the data by dimensions such as:

- Host
- Protocol
- Port
- Time
- Conversation
- Application
- TCP flags

For example, investigating an HTTPS connection can begin with:

`tcp.port == 443`

The analyst can then identify individual conversations and examine their TCP behavior.

## TCP streams

A TCP stream represents a bidirectional conversation between two transport endpoints.

For example:

`192.168.1.25:53142 <-> 93.184.216.34:443`

Packets traveling in either direction can belong to the same conversation.

The Python, JavaScript, and C++ implementations group packets using normalized endpoint pairs.

## Conversation analysis

A conversation can reveal:

- Connection establishment
- Application requests
- Responses
- Packet ordering
- Delays
- Retransmissions
- Connection termination
- Resets

This is often more useful than examining isolated packets.

A single packet can provide a fact. A sequence of packets can reveal behavior.

## Latency

Latency is the time required for information to travel through a system or for a response to occur.

Packet captures provide timestamps that can be used to measure observed delays.

Possible measurements include:

- Inter-packet delay
- TCP handshake duration
- DNS query-response delay
- Application request-response delay
- Time between retransmission attempts

Latency must be interpreted carefully because capture timestamps depend on where and how the traffic was captured.

## Throughput

Throughput represents the rate at which data is transferred.

A basic calculation is:

`throughput = transferred bits / elapsed seconds`

For example, transferring 125,000,000 bytes in 10 seconds produces:

`1,000,000,000 bits / 10 seconds = 100,000,000 bits/s`

which is:

`100 Mbps`

Observed throughput is affected by protocol overhead, congestion, latency, packet loss, processing capacity, and the behavior of the communicating applications.

## Bandwidth versus throughput

Bandwidth describes the capacity of a communication path or link.

Throughput describes the amount of useful data actually transferred over time.

A link advertised as 1 Gbps does not guarantee that an application will achieve exactly 1 Gbps of application throughput.

Factors such as overhead, packet loss, latency, protocol behavior, server performance, and congestion affect the observed result.

## Packet loss

Packet loss occurs when packets fail to reach their intended destination.

Possible causes include:

- Congestion
- Faulty links
- Wireless interference
- Hardware problems
- Queue overflow
- Routing problems
- Intentional filtering

TCP attempts to recover from loss through retransmission mechanisms.

UDP itself does not automatically retransmit lost datagrams.

The application may implement its own reliability system if required.

## MTU

MTU stands for Maximum Transmission Unit.

A common Ethernet MTU is 1500 bytes for the IP packet size, although actual configurations and technologies vary.

If a packet exceeds the relevant MTU, the system may need to fragment it, reject it, or otherwise handle the size constraint depending on protocol version and path behavior.

IPv4 and IPv6 differ significantly in fragmentation behavior.

Path MTU Discovery can be used to determine a suitable packet size for a path.

## Checksums

Checksums provide error-detection capabilities.

The Internet checksum used by several Internet protocols is based on one's-complement arithmetic.

The Python and C++ implementations demonstrate a simplified Internet checksum calculation.

A checksum is not equivalent to cryptographic integrity.

A checksum is generally intended for detecting accidental corruption rather than protecting against a capable attacker.

## Hashes and cryptographic integrity

Cryptographic hashes such as SHA-256 have stronger properties than ordinary transport checksums.

They can be used as components of integrity systems.

The JavaScript implementation demonstrates SHA-256 using Node.js's built-in `crypto` module.

A hash alone does not automatically authenticate a message. Authentication generally requires an appropriate cryptographic construction and key management.

## HTTP

HTTP is an application-layer protocol used extensively for web communication.

A simple HTTP request contains a request line and headers.

For example, the conceptual structure is:

`GET /index.html HTTP/1.1`

followed by headers such as:

`Host: example.test`

An HTTP message may also contain a body.

The JavaScript and C++ implementations parse basic HTTP request structure.

## HTTPS

HTTPS is HTTP protected by TLS.

TLS provides cryptographic mechanisms for:

- Confidentiality
- Integrity
- Authentication of the server through certificates and the TLS trust model

Packet captures of HTTPS traffic can still reveal metadata such as:

- Source and destination IP
- Ports
- Packet sizes
- Timing
- Connection patterns

Encryption generally prevents an ordinary observer from directly reading the protected HTTP payload.

## HTTP/3 and QUIC

Traditional HTTP/1.1 and HTTP/2 deployments commonly use TCP.

HTTP/3 uses QUIC.

QUIC operates over UDP and incorporates transport functionality such as reliability and stream management above UDP.

This means that seeing UDP traffic does not necessarily mean the traffic is a simple DNS-style datagram exchange.

Modern protocol analysis requires identifying the higher-level protocol where possible.

## Network troubleshooting

A systematic troubleshooting process prevents random experimentation.

A practical order is:

1. Check physical or wireless connectivity.
2. Check the host's IP address.
3. Check the subnet configuration.
4. Check the default gateway.
5. Test local reachability.
6. Check DNS resolution.
7. Inspect routing.
8. Check transport ports.
9. Inspect application behavior.
10. Check firewall and access-control policies.
11. Inspect timing, retransmissions and resets.

The exact order can change depending on the problem.

## Physical and link-layer problems

Possible symptoms include:

- No link
- Interface down
- Wireless association failure
- High error rates
- Incorrect VLAN configuration
- Switch-port problems

Packet capture may be impossible or incomplete if the host never obtains functioning network connectivity.

## IP configuration problems

Common problems include:

- Incorrect IP address
- Incorrect subnet prefix
- Duplicate IP address
- Incorrect default gateway
- Incorrect DNS configuration

A host may be able to communicate with some devices while being unable to reach others because of subnet or routing configuration.

## DNS problems

If a browser cannot reach `example.com`, the first question should not automatically be "Is the Internet down?"

DNS resolution may have failed while the network path remains functional.

A packet capture can reveal whether:

- A DNS request was sent.
- A DNS response arrived.
- The response contained an error.
- The application used another resolver.
- The connection proceeded to an unexpected destination.

## TCP troubleshooting

The TCP handshake provides useful evidence.

### SYN with no SYN-ACK

Possible explanations include:

- Destination unreachable
- Firewall filtering
- Routing problem
- Server unavailable
- Incorrect address
- Capture point limitations

### SYN followed by RST

Possible explanations include:

- No listening service
- Active rejection
- Firewall behavior
- Application or operating-system decision

### Successful handshake but slow application response

Possible explanations include:

- Server processing delay
- Application-level bottleneck
- Database latency
- Network congestion
- Packet loss
- Protocol negotiation
- Backend dependency failure

Packet evidence should be correlated with server and application evidence.

## Retransmissions and duplicate acknowledgements

TCP packet captures can show patterns associated with loss and recovery.

An analyst may inspect:

- Sequence numbers
- Acknowledgement numbers
- Timing
- Duplicate acknowledgements
- Retransmitted segments
- Window advertisements

These fields help determine whether the problem appears to involve transport reliability or application processing.

## Security considerations

Network captures may contain sensitive information.

Potentially sensitive information includes:

- IP addresses
- MAC addresses
- Hostnames
- Internal infrastructure details
- Authentication information
- Cookies
- Unencrypted application content
- Application metadata
- Communication patterns

Capture files should therefore be treated as potentially sensitive data.

Encryption reduces payload visibility but does not necessarily hide:

- Source IP
- Destination IP
- Port
- Packet size
- Timing
- Traffic volume
- Connection patterns

Security analysis should distinguish content confidentiality from metadata confidentiality.

## Packet capture permissions

Capturing traffic often requires elevated operating-system privileges or appropriate access to a capture interface.

A production organization should control who can perform captures and who can access resulting capture files.

Capturing traffic without authorization can violate organizational policies, contracts, privacy requirements, or applicable law.

The examples in this repository use simulated packet data rather than live traffic.

## Wireshark analysis of encrypted traffic

When traffic is protected by TLS, a packet analyzer may still identify:

- TCP connection establishment
- TLS-related records
- Connection duration
- Packet sizes
- Retransmissions
- TCP window behavior
- Addresses and ports

The exact visible information depends on the protocol version, encryption technology, capture position, and available decryption information.

## Performance considerations

The Python packet analyzer uses lists, dictionaries, `Counter`, and filtering operations.

Many simple filtering operations are approximately `O(n)` over the number of captured packets.

If the same capture must be queried repeatedly at very large scale, indexing can reduce lookup costs.

Possible indexes include:

- Source IP
- Destination IP
- Protocol
- Port
- TCP stream
- Timestamp

A production packet-analysis system may require memory-efficient storage, streaming processing, indexing, parallel processing, or specialized capture formats.

## C++ performance design

The C++ case study uses standard-library containers such as:

- `vector`
- `map`
- `unordered_map`
- `optional`
- `array`

`vector` provides efficient sequential storage and iteration.

`map` provides ordered associative lookup.

`unordered_map` provides average constant-time hash lookup when its assumptions hold.

The C++ implementation favors clarity and strong typing rather than implementing a production-scale packet engine.

## JavaScript performance design

JavaScript uses:

- `Map`
- `Buffer`
- Arrays
- Classes
- Callback-based asynchronous DNS APIs

Node.js is particularly useful for demonstrating event-driven network applications.

Network applications often spend substantial time waiting for I/O. An event-driven runtime can continue processing other work while waiting for asynchronous operations such as DNS resolution or network communication.

## Python performance design

Python provides concise data structures and high-level networking utilities.

It is particularly useful for:

- Packet analysis scripts
- Automation
- Protocol experiments
- Data processing
- Network diagnostics
- Rapid prototyping

For very large packet-processing workloads, computationally expensive operations may require optimized libraries, native extensions, vectorization, multiprocessing, or specialized packet-processing systems.

## Error handling

Network programs must expect failure.

Potential failures include:

- Invalid addresses
- Invalid ports
- DNS errors
- Connection refusal
- Connection timeout
- Packet loss
- Malformed protocol data
- Unexpected protocol states
- Permission problems
- Resource exhaustion

The Python implementation uses exceptions and validation.

The JavaScript implementation uses exceptions and explicit error callbacks.

The C++ implementation uses exceptions and validates critical inputs.

## Edge cases

Important networking edge cases include:

- Port `0`
- Port `65535`
- Invalid IPv4 octets
- `/0` routes
- `/32` host routes
- Empty payloads
- Odd-length checksum input
- Packets without transport ports, such as ICMP
- Encrypted application payloads
- Fragmented traffic
- Duplicate packets
- Retransmissions
- Connection resets
- Missing DNS responses
- Multiple routes matching the same destination

A packet-analysis system should not assume that every packet has the same fields.

## Why ICMP packets do not have TCP or UDP ports

ICMP is not TCP or UDP.

A packet such as an ICMP Echo Request therefore does not contain TCP or UDP source and destination ports.

The packet models in this project use optional port fields to represent this distinction.

This is an example of why packet analyzers must represent protocol-specific fields rather than forcing every packet into one common structure.

## Why DNS is not always UDP

DNS is frequently associated with UDP port 53, but DNS can also use TCP.

TCP can be used for:

- Large responses
- Zone transfers
- Situations requiring reliable connection-oriented transport
- Other protocol-specific requirements

Modern DNS deployments can also use encrypted DNS technologies and other transport arrangements.

Therefore, identifying traffic only by port is not always sufficient for protocol classification.

## Why port numbers do not prove application identity

Port numbers provide useful evidence but are not absolute proof of the application.

Applications can use non-standard ports.

A service commonly associated with port 443 may not necessarily be ordinary HTTPS.

A packet analyzer can use protocol signatures, payload structure, negotiation information, and other evidence to improve protocol identification.

## Routing versus switching

Switching and routing are related but distinct.

A simplified comparison is:

| Function | Primary information |
|---|---|
| Switching | MAC addresses and link-layer information |
| Routing | IP addresses and network prefixes |

A switch forwards frames within a local network.

A router forwards packets between IP networks.

Modern enterprise devices may perform both functions.

## Hub versus switch

A hub repeats incoming signals to multiple interfaces.

A switch makes forwarding decisions using MAC-address information.

A switch can therefore reduce unnecessary delivery of frames compared with a hub.

Hubs are largely obsolete in modern switched Ethernet networks.

## Client ephemeral ports

A client commonly uses a temporary source port when initiating a connection.

For example:

`192.168.1.25:53142 -> 93.184.216.34:443`

The server listens on a known service port while the client uses a temporary port.

This four-part endpoint relationship is important when identifying conversations.

## Production packet-analysis considerations

A production monitoring platform may need to handle:

- Large capture files
- High packet rates
- Timestamp precision
- Packet loss at the capture layer
- Storage limits
- Compression
- Indexing
- Protocol decoding
- IPv4 and IPv6
- VLAN tags
- Tunnels
- Encapsulation
- Encrypted protocols
- Distributed capture points
- Access control
- Sensitive data management
- Alerting
- Long-term retention

The educational implementation deliberately avoids those production-scale complexities while modeling the underlying concepts.

## Python implementation

The Python program is organized as a networking laboratory.

It demonstrates:

- IPv4 parsing using `ipaddress`
- IPv4 binary representation
- CIDR networks
- MAC-address normalization
- Port classification
- Socket endpoint representation
- Protocol layering
- Encapsulation
- TCP flags
- TCP handshake construction
- TCP sequence and acknowledgement behavior
- UDP datagrams
- DNS resolution
- ARP cache concepts
- ICMP messages
- Routing-table lookup
- Longest-prefix matching
- NAT mapping
- Firewall evaluation
- Packet records
- Packet filtering
- Wireshark-style filter expressions
- TCP stream grouping
- Latency measurement
- Throughput calculation
- Packet-loss simulation
- Internet checksum calculation
- IPv4 header construction
- HTTP request analysis
- Packet dissection
- Troubleshooting
- Self-tests

The program is intentionally self-contained and uses the Python standard library.

### Python packet model

The `Packet` class represents a simplified captured packet.

Its fields include:

- Packet number
- Timestamp
- Source MAC
- Destination MAC
- Source IP
- Destination IP
- Transport protocol
- Source port
- Destination port
- TCP flags
- Payload
- Application protocol
- Informational description

Optional port and flag fields are important because not every network protocol has TCP-style ports or TCP flags.

### Python routing implementation

The `RoutingTable` class evaluates matching routes and chooses the route with the longest prefix.

This models the central principle of IP routing without implementing the full complexity of an operating-system or router routing stack.

### Python firewall implementation

The `SimpleFirewall` class evaluates source network, destination port, and protocol.

It demonstrates:

- Explicit allow rules
- Explicit deny rules
- Rule ordering
- Implicit deny

Real firewalls can use substantially more sophisticated state and policy information.

## JavaScript implementation

The JavaScript implementation complements the Python program by using Node.js features.

It demonstrates:

- JavaScript classes
- `Map`
- `Buffer`
- IPv4 conversion
- CIDR calculations
- MAC-address parsing
- Port representation
- Socket endpoints
- Encapsulation
- TCP flags
- TCP handshake
- UDP datagrams
- Simulated DNS
- Asynchronous DNS lookup
- Routing
- Firewall rules
- NAT
- Packet objects
- Packet filtering
- TCP stream grouping
- Throughput
- Timing
- Checksums
- HTTP parsing
- SHA-256 hashing
- Node.js TCP socket creation
- Self-tests

### JavaScript buffers

Node.js `Buffer` objects are useful for networking because network protocols operate on bytes rather than only on human-readable strings.

The implementation uses buffers for:

- MAC-address conversion
- Packet payloads
- Checksums
- HTTP payload representation
- Cryptographic hashing

This provides a closer relationship to actual network data than using strings for everything.

### JavaScript asynchronous DNS

Node.js DNS APIs demonstrate asynchronous execution.

DNS resolution can involve network I/O and therefore may complete later than the code that initiated the operation.

The example uses a callback to process the result.

This demonstrates a central principle of event-driven networking applications: I/O operations may not complete immediately.

## C++ case study

The C++ program models an enterprise network monitoring and troubleshooting system.

The scenario contains:

- A client at `192.168.1.25`
- A gateway at `192.168.1.1`
- An external web server
- An external DNS server
- A local `/24` network
- TCP HTTPS traffic
- UDP DNS traffic
- ICMP diagnostic traffic

The monitoring system receives simulated packet records and performs several forms of analysis.

## C++ design

The case study is divided into components.

### `IPv4Address`

Represents a 32-bit IPv4 address.

Responsibilities include:

- Parsing dotted-decimal notation
- Storing the numeric address
- Converting back to dotted-decimal text
- Comparing addresses

### `IPv4Network`

Represents an IPv4 network and prefix length.

It provides:

- Network calculation
- Prefix length
- Address containment
- CIDR representation

### `MacAddress`

Represents a six-byte MAC address.

It provides:

- Text parsing
- Normalized formatting
- Comparison

### `Port`

Represents a 16-bit TCP or UDP port.

It also identifies common service associations.

### `TCPSegment`

Represents:

- Source port
- Destination port
- Sequence number
- Acknowledgement number
- Flags
- Window size
- Payload

### `UDPDatagram`

Represents UDP source and destination ports and application payload.

### `Route`

Represents:

- Destination network
- Optional next hop
- Interface
- Metric

### `RoutingTable`

Performs longest-prefix route selection.

### `FirewallRule`

Represents a simplified security policy.

### `Firewall`

Evaluates packets against rules and implements implicit deny behavior.

### `NATEntry`

Models a translation between internal and externally visible endpoints.

### `Packet`

Represents a captured packet.

It contains link, network, transport, and application information.

### `PacketAnalyzer`

Provides:

- Protocol counts
- Application counts
- Top talkers
- Protocol filtering
- Port filtering
- IP filtering
- Application filtering

## C++ routing case study

The routing table contains:

`192.168.1.0/24`

`10.0.0.0/8`

`0.0.0.0/0`

A destination is tested against each route.

If multiple routes match, the route with the longest prefix is selected.

This demonstrates why a `/24` route takes precedence over a `/0` default route for an address inside the `/24`.

## C++ firewall case study

The firewall contains a rule allowing TCP port 443 from the local network.

It also contains a rule denying TCP port 22.

If no rule matches, the implementation returns an implicit deny.

This models the security principle that traffic should not automatically become allowed merely because no explicit policy exists.

## C++ TCP stream grouping

The program normalizes the two endpoints of TCP packets and creates a bidirectional conversation key.

For example:

`192.168.1.25:53142 <-> 93.184.216.34:443`

Both directions of the connection can therefore be grouped into one logical stream.

This is conceptually similar to how packet-analysis tools organize conversations.

## C++ HTTP parsing

The case study parses:

- HTTP method
- Request path
- HTTP version
- Headers

It does not attempt to implement a complete HTTP parser.

The implementation is intentionally limited to the basic structure needed to demonstrate packet-level application analysis.

## C++ checksum implementation

The program implements the Internet checksum algorithm using 16-bit words and one's-complement arithmetic.

This demonstrates how protocol fields can depend on binary calculations.

A production implementation would need to follow the exact checksum rules for the protocol and header being constructed.

## Wireshark concepts represented by the project

The project does not implement the complete Wireshark application.

Instead, it models several concepts that make Wireshark useful:

- Packet lists
- Packet fields
- Protocol decoding
- Display filtering
- TCP conversation grouping
- Traffic statistics
- Timing analysis
- Application identification
- Protocol-layer inspection

The examples are designed to make the underlying networking concepts understandable independently of a specific packet-analysis interface.

## Packet-analysis reasoning

A strong packet-analysis workflow does not start by looking randomly through every packet.

A better approach is to define the question.

Examples:

- Why did the TCP connection fail?
- Why is DNS resolution slow?
- Why is the application response delayed?
- Is packet loss occurring?
- Which service is communicating with this host?
- Which route is being used?
- Is a firewall blocking traffic?
- What is visible even though the application uses encryption?

Once the question is defined, filters and packet fields can be selected deliberately.

## Example: analyzing a failed TCP connection

Suppose a client tries to connect to a server.

First identify the client's SYN.

Then look for:

`SYN -> SYN/ACK -> ACK`

If no SYN-ACK appears, investigate:

- Routing
- Firewall filtering
- Server availability
- Address configuration
- Capture location

If a SYN-ACK appears but the final ACK does not, investigate the client path, filtering, or asymmetric behavior.

If the handshake completes but the application does not respond, move the investigation into the application layer.

## Example: analyzing DNS

Identify DNS traffic.

Inspect:

- Query name
- Query type
- Source
- Destination
- Response
- Response code
- Timing

Then determine whether the application attempted to connect after receiving the DNS response.

This separates name-resolution problems from application-connection problems.

## Example: analyzing HTTPS

Filter for TCP port 443 when analyzing traditional HTTPS over TCP.

Inspect:

- TCP handshake
- TLS negotiation
- Connection timing
- Retransmissions
- Packet sizes
- Connection termination

The application payload will generally not be available as ordinary plaintext because TLS protects it.

The analyst can still identify network-level problems without reading the HTTP content.

## Example: analyzing packet loss

Look for:

- Missing sequence progress
- Duplicate acknowledgements
- Retransmissions
- Increased delays
- TCP recovery behavior

Packet loss can affect throughput because retransmission consumes bandwidth and congestion-control behavior can reduce the sending rate.

## Common mistakes

### Treating IP and MAC addresses as interchangeable

They operate at different networking layers.

### Assuming port 443 proves HTTPS

Port numbers are strong clues but do not guarantee application identity.

### Assuming DNS always uses UDP

DNS can use TCP and other transport mechanisms.

### Assuming every packet has ports

ICMP packets do not use TCP or UDP ports.

### Assuming a packet capture shows everything

The capture point, capture configuration, network architecture, encryption, and traffic visibility all matter.

### Confusing bandwidth with throughput

A link's nominal capacity does not guarantee application-level throughput.

### Treating every TCP retransmission as proof of a broken cable

Retransmissions can have multiple causes.

### Ignoring timestamps

Timing often reveals behavior that cannot be understood from packet contents alone.

### Filtering too aggressively during capture

Important evidence may be permanently excluded.

### Treating encryption as total invisibility

Encryption protects payload contents but does not necessarily hide network metadata.

## Limitations of the implementations

These implementations are educational models rather than complete packet-analysis systems.

They do not provide:

- Full Ethernet capture
- Native packet sniffing
- Complete Wireshark protocol dissectors
- Full IPv6 implementation
- Full TCP implementation
- Complete DNS protocol implementation
- Complete TLS implementation
- Complete firewall state tracking
- Hardware-level network interfaces
- Full fragmentation and reassembly
- Full protocol negotiation
- High-performance packet capture
- Distributed capture
- Production storage systems

The simplified models intentionally isolate important networking principles.

## Important implementation distinctions

### Python

Python emphasizes clarity and rapid experimentation.

It is particularly suitable for:

- Network automation
- Analysis scripts
- Educational simulations
- Data processing
- Diagnostic tools

### JavaScript

Node.js emphasizes event-driven application development.

It is particularly useful for:

- Network services
- APIs
- Asynchronous I/O
- Web applications
- Event-driven systems
- Binary data processing through buffers

### C++

C++ provides strong control over memory, data representation, and performance.

It is suitable for:

- Network infrastructure
- High-performance packet processing
- Systems software
- Network appliances
- Low-level protocol implementations
- Performance-sensitive analysis

## Real-world applications

Networking fundamentals and packet analysis are relevant to:

- Enterprise networking
- Cloud infrastructure
- Data centers
- Cybersecurity
- Security operations
- Network operations
- Application performance monitoring
- Incident response
- Digital forensics
- DevOps
- Site reliability engineering
- Distributed systems
- Internet services
- Wireless networking
- IoT systems
- Telecommunications

Understanding packets makes it possible to connect high-level application symptoms with lower-level network behavior.

## Layered troubleshooting model

A useful conceptual model is:

`Application`

↓

`Transport`

↓

`Internet`

↓

`Link`

↓

`Physical`

A problem can originate at any layer.

For example:

- A web application can fail even when TCP is functioning.
- TCP can fail even when IP addressing is correct.
- IP communication can fail even when Ethernet is working.
- Ethernet communication can fail because the physical link is unavailable.

Packet analysis becomes powerful when observations are interpreted according to this layered structure.

## Practical distinctions

### Router versus switch

A switch primarily forwards link-layer frames.

A router primarily forwards network-layer packets between networks.

### TCP versus UDP

TCP provides connection-oriented reliable transport.

UDP provides connectionless datagrams.

### Packet versus frame

A packet is commonly associated with the network layer.

A frame is associated with the link layer.

### Capture filter versus display filter

A capture filter affects what is collected.

A display filter affects what is displayed from collected traffic.

### Checksum versus cryptographic hash

A checksum is primarily designed for efficient error detection.

A cryptographic hash provides much stronger integrity properties but does not itself provide authentication.

### Encryption versus metadata protection

Encryption protects the encrypted payload.

It does not necessarily hide addresses, ports, timing, packet sizes, or traffic volume.

## Best practices

For network analysis:

- Define the investigation question first.
- Capture from an appropriate observation point.
- Record accurate timestamps.
- Preserve original captures when possible.
- Use narrow display filters after collecting sufficient evidence.
- Analyze both directions of a conversation.
- Check TCP state before interpreting application behavior.
- Examine DNS separately from application connections.
- Correlate packet observations with host logs and application metrics.
- Treat packet captures as sensitive data.
- Avoid drawing conclusions from a single packet when a sequence is required.
- Distinguish observed facts from hypotheses about the cause.

## Core reference

The essential conceptual chain is:

`Application data`

↓

`Transport protocol`

↓

`IP packet`

↓

`Link-layer frame`

↓

`Physical transmission`

At the receiving side:

`Physical transmission`

↓

`Link-layer frame`

↓

`IP packet`

↓

`Transport protocol`

↓

`Application data`

Ports identify transport endpoints.

IP addresses identify logical network endpoints.

MAC addresses identify link-layer endpoints.

Protocols define communication behavior.

Routers move packets between networks.

Switches move frames within local networks.

Packet-analysis tools expose these layers so that network behavior can be examined at the level where the problem occurs.
