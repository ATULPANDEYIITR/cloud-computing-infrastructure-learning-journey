"""
Networking Fundamentals and Wireshark Concepts
================================================

A self-contained study and demonstration program covering:

1. Networks and network communication
2. Clients and servers
3. Packets, frames, segments, and datagrams
4. Protocols and protocol layering
5. MAC addresses and IP addresses
6. IPv4 subnetting and CIDR
7. TCP and UDP
8. Ports and sockets
9. DNS, DHCP, ARP, ICMP, HTTP, HTTPS
10. Network devices
11. Routing and switching
12. NAT
13. Firewalls
14. Encapsulation and decapsulation
15. Packet construction and inspection
16. TCP connection behavior
17. DNS resolution simulation
18. Routing-table decisions
19. Wireshark concepts and display-filter logic
20. Troubleshooting methodology
21. Security considerations
22. Performance and reliability concepts

The program uses only the Python standard library.
It does not capture live traffic. Instead, it builds and analyzes
representative packet structures so that the networking concepts can
be studied safely and reproducibly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import ipaddress
import random
import socket
import struct
import time
from collections import Counter, defaultdict, deque
from typing import Iterable, Optional


# ============================================================================
# SECTION 1: BASIC NETWORK TERMINOLOGY
# ============================================================================

def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def subsection(title: str) -> None:
    print("\n" + "-" * 78)
    print(title)
    print("-" * 78)


section("NETWORKING FUNDAMENTALS")

print(
    """
A computer network is a collection of connected devices that exchange data.

Important terms:

  Host       - A device participating in network communication.
  Client     - A host that requests a service.
  Server     - A host that provides a service.
  Protocol   - A defined set of communication rules.
  Packet     - A unit of network-layer data.
  Frame      - A link-layer unit carrying a packet on a local network.
  Segment    - A TCP transport-layer unit.
  Datagram   - A UDP transport-layer unit.
  Port       - A logical endpoint identifying an application/service.
  Socket     - A communication endpoint commonly identified by IP + port.
  Router     - A device that forwards traffic between IP networks.
  Switch     - A device that forwards Ethernet frames within a LAN.
  Access Point - A device providing wireless LAN connectivity.
  Firewall   - A system that applies rules to network traffic.
"""
)


# ============================================================================
# SECTION 2: NETWORK ADDRESSING
# ============================================================================

section("IP ADDRESSING")

subsection("IPv4 addresses")

ipv4_examples = [
    "192.168.1.10",
    "10.0.0.25",
    "172.16.4.8",
    "8.8.8.8",
]

for address in ipv4_examples:
    ip = ipaddress.ip_address(address)
    print(
        f"{address:15} version={ip.version} "
        f"private={ip.is_private} loopback={ip.is_loopback}"
    )


subsection("IPv4 address structure")

def show_ipv4_binary(address: str) -> None:
    ip = ipaddress.IPv4Address(address)
    binary = format(int(ip), "032b")
    octets = [binary[i:i + 8] for i in range(0, 32, 8)]
    print(f"{address} -> {' '.join(octets)}")


show_ipv4_binary("192.168.1.10")
show_ipv4_binary("10.0.0.25")


subsection("CIDR and subnetting")

networks = [
    "192.168.1.0/24",
    "192.168.1.64/26",
    "10.10.0.0/16",
    "172.16.20.0/28",
]

for network_text in networks:
    network = ipaddress.ip_network(network_text, strict=False)
    hosts = list(network.hosts())
    print(f"\nNetwork: {network}")
    print(f"  Network address : {network.network_address}")
    print(f"  Broadcast       : {network.broadcast_address}")
    print(f"  Prefix length   : /{network.prefixlen}")
    print(f"  Subnet mask     : {network.netmask}")
    print(f"  Total addresses : {network.num_addresses}")
    print(f"  Usable hosts    : {len(hosts)}")
    if hosts:
        print(f"  First host      : {hosts[0]}")
        print(f"  Last host       : {hosts[-1]}")


def same_subnet(address_a: str, address_b: str, prefix_length: int) -> bool:
    """
    Two addresses are in the same subnet when applying the same prefix
    produces the same network address.
    """
    network_a = ipaddress.ip_network(
        f"{address_a}/{prefix_length}",
        strict=False,
    )
    network_b = ipaddress.ip_network(
        f"{address_b}/{prefix_length}",
        strict=False,
    )
    return network_a.network_address == network_b.network_address


print(
    "\n192.168.1.10 and 192.168.1.200 in /24:",
    same_subnet("192.168.1.10", "192.168.1.200", 24),
)

print(
    "192.168.1.10 and 192.168.2.10 in /24:",
    same_subnet("192.168.1.10", "192.168.2.10", 24),
)


# ============================================================================
# SECTION 3: MAC ADDRESSES
# ============================================================================

section("MAC ADDRESSES")

MAC_LENGTH = 6


def normalize_mac(mac: str) -> str:
    """
    Accept common MAC-address formats and normalize them.

    Example:
        aa-bb-cc-dd-ee-ff
        aa:bb:cc:dd:ee:ff
        aabbccddeeff
    """
    cleaned = mac.replace(":", "").replace("-", "").replace(".", "")
    if len(cleaned) != 12:
        raise ValueError("A MAC address must contain 12 hexadecimal digits.")

    int(cleaned, 16)
    return ":".join(cleaned[i:i + 2] for i in range(0, 12, 2)).lower()


def mac_to_bytes(mac: str) -> bytes:
    return bytes.fromhex(normalize_mac(mac).replace(":", ""))


def bytes_to_mac(value: bytes) -> str:
    if len(value) != MAC_LENGTH:
        raise ValueError("A MAC address contains exactly six bytes.")
    return ":".join(f"{byte:02x}" for byte in value)


mac = normalize_mac("AA-BB-CC-DD-EE-FF")
print("Normalized MAC:", mac)
print("MAC bytes:", mac_to_bytes(mac))
print("Back to text:", bytes_to_mac(mac_to_bytes(mac)))


# ============================================================================
# SECTION 4: PORTS AND SOCKETS
# ============================================================================

section("PORTS AND SOCKETS")

COMMON_PORTS = {
    20: "FTP data",
    21: "FTP control",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    67: "DHCP server",
    68: "DHCP client",
    80: "HTTP",
    110: "POP3",
    123: "NTP",
    143: "IMAP",
    161: "SNMP",
    443: "HTTPS",
    3389: "RDP",
}


def describe_port(port: int) -> str:
    if not 0 <= port <= 65535:
        raise ValueError("TCP and UDP ports range from 0 through 65535.")

    if port in COMMON_PORTS:
        return COMMON_PORTS[port]

    if port <= 1023:
        category = "well-known range"
    elif port <= 49151:
        category = "registered range"
    else:
        category = "dynamic/private range"

    return category


for port in [22, 53, 80, 443, 50000]:
    print(f"Port {port:5}: {describe_port(port)}")


@dataclass(frozen=True)
class SocketEndpoint:
    ip_address: str
    port: int
    protocol: str

    def __post_init__(self) -> None:
        ipaddress.ip_address(self.ip_address)
        if not 0 <= self.port <= 65535:
            raise ValueError("Invalid port.")
        if self.protocol.upper() not in {"TCP", "UDP"}:
            raise ValueError("Protocol must be TCP or UDP.")

    def __str__(self) -> str:
        return f"{self.protocol.upper()} {self.ip_address}:{self.port}"


client_endpoint = SocketEndpoint("192.168.1.25", 53142, "TCP")
server_endpoint = SocketEndpoint("93.184.216.34", 443, "TCP")

print("\nClient socket :", client_endpoint)
print("Server socket :", server_endpoint)


# ============================================================================
# SECTION 5: PROTOCOL LAYERS
# ============================================================================

section("PROTOCOL STACK AND ENCAPSULATION")

LAYERS = [
    ("Application", ["HTTP", "HTTPS", "DNS", "DHCP", "SSH", "SMTP"]),
    ("Transport", ["TCP", "UDP"]),
    ("Internet", ["IPv4", "IPv6", "ICMP"]),
    ("Link", ["Ethernet", "Wi-Fi", "ARP"]),
]

for layer_name, protocols in LAYERS:
    print(f"{layer_name:12}: {', '.join(protocols)}")


@dataclass
class ApplicationData:
    protocol: str
    payload: bytes


@dataclass
class TransportSegment:
    protocol: str
    source_port: int
    destination_port: int
    payload: bytes


@dataclass
class IPPacket:
    source_ip: str
    destination_ip: str
    protocol: str
    payload: bytes


@dataclass
class EthernetFrame:
    source_mac: str
    destination_mac: str
    ether_type: int
    payload: bytes


def encapsulate_demo() -> None:
    """
    Demonstrates conceptual encapsulation:

        Application data
              ↓
        TCP/UDP segment
              ↓
        IP packet
              ↓
        Ethernet frame

    Each layer adds metadata required by the corresponding network
    mechanism.
    """
    application = ApplicationData(
        protocol="HTTP",
        payload=b"GET /index.html HTTP/1.1\r\nHost: example.test\r\n\r\n",
    )

    transport = TransportSegment(
        protocol="TCP",
        source_port=53142,
        destination_port=80,
        payload=application.payload,
    )

    network = IPPacket(
        source_ip="192.168.1.25",
        destination_ip="93.184.216.34",
        protocol="TCP",
        payload=transport.payload,
    )

    frame = EthernetFrame(
        source_mac="00:11:22:33:44:55",
        destination_mac="aa:bb:cc:dd:ee:ff",
        ether_type=0x0800,
        payload=network.payload,
    )

    print("\nApplication payload:", application.payload)
    print(
        "Transport:",
        transport.protocol,
        transport.source_port,
        "->",
        transport.destination_port,
    )
    print(
        "IP:",
        network.source_ip,
        "->",
        network.destination_ip,
        network.protocol,
    )
    print(
        "Ethernet:",
        frame.source_mac,
        "->",
        frame.destination_mac,
        f"EtherType=0x{frame.ether_type:04x}",
    )


encapsulate_demo()


# ============================================================================
# SECTION 6: TCP
# ============================================================================

section("TCP")

TCP_FLAGS = {
    "SYN": 0x02,
    "ACK": 0x10,
    "FIN": 0x01,
    "RST": 0x04,
    "PSH": 0x08,
}


def flags_to_text(flags: int) -> str:
    names = [
        name
        for name, value in TCP_FLAGS.items()
        if flags & value
    ]
    return ", ".join(names) if names else "NONE"


@dataclass
class TCPSegment:
    source_port: int
    destination_port: int
    sequence_number: int
    acknowledgement_number: int
    flags: int
    window_size: int
    payload: bytes = b""

    @property
    def payload_length(self) -> int:
        return len(self.payload)

    def describe(self) -> str:
        return (
            f"{self.source_port} -> {self.destination_port}, "
            f"seq={self.sequence_number}, "
            f"ack={self.acknowledgement_number}, "
            f"flags=[{flags_to_text(self.flags)}], "
            f"window={self.window_size}, "
            f"payload={self.payload_length} bytes"
        )


def simulate_tcp_handshake() -> list[TCPSegment]:
    """
    TCP normally establishes a connection with a three-way handshake:

        Client -> Server : SYN
        Server -> Client : SYN + ACK
        Client -> Server : ACK
    """
    client_port = 53142
    server_port = 443
    client_sequence = 1000
    server_sequence = 5000

    segments = [
        TCPSegment(
            client_port,
            server_port,
            client_sequence,
            0,
            TCP_FLAGS["SYN"],
            64240,
        ),
        TCPSegment(
            server_port,
            client_port,
            server_sequence,
            client_sequence + 1,
            TCP_FLAGS["SYN"] | TCP_FLAGS["ACK"],
            65535,
        ),
        TCPSegment(
            client_port,
            server_port,
            client_sequence + 1,
            server_sequence + 1,
            TCP_FLAGS["ACK"],
            64240,
        ),
    ]

    return segments


print("\nTCP three-way handshake:")
for number, segment in enumerate(simulate_tcp_handshake(), start=1):
    print(f"  {number}. {segment.describe()}")


subsection("TCP sequence and acknowledgement example")

data = b"HELLO"
first_data = TCPSegment(
    53142,
    443,
    sequence_number=1001,
    acknowledgement_number=5001,
    flags=TCP_FLAGS["ACK"] | TCP_FLAGS["PSH"],
    window_size=64240,
    payload=data,
)

acknowledgement = TCPSegment(
    443,
    53142,
    sequence_number=5001,
    acknowledgement_number=1001 + len(data),
    flags=TCP_FLAGS["ACK"],
    window_size=65535,
)

print("Data segment:", first_data.describe())
print("Acknowledgement:", acknowledgement.describe())


# ============================================================================
# SECTION 7: UDP
# ============================================================================

section("UDP")

@dataclass
class UDPSegment:
    source_port: int
    destination_port: int
    payload: bytes

    @property
    def payload_length(self) -> int:
        return len(self.payload)

    def describe(self) -> str:
        return (
            f"{self.source_port} -> {self.destination_port}, "
            f"payload={self.payload_length} bytes"
        )


dns_query = UDPSegment(
    source_port=53000,
    destination_port=53,
    payload=b"example.test",
)

print("DNS-style UDP datagram:", dns_query.describe())

print(
    """
TCP provides connection-oriented transport with sequencing,
acknowledgements, retransmission, and flow/congestion mechanisms.

UDP provides a connectionless datagram service with much less
transport-layer overhead. Applications choose UDP when its properties
fit the workload, such as DNS queries, real-time media, and some
interactive protocols.
"""
)


# ============================================================================
# SECTION 8: DNS
# ============================================================================

section("DNS")

DNS_RECORDS = {
    "example.test": {
        "A": "192.0.2.10",
        "AAAA": "2001:db8::10",
    },
    "api.example.test": {
        "A": "192.0.2.20",
    },
}


def dns_lookup(name: str, record_type: str = "A") -> Optional[str]:
    records = DNS_RECORDS.get(name.lower())
    if not records:
        return None
    return records.get(record_type.upper())


for hostname in ["example.test", "api.example.test", "missing.test"]:
    print(
        hostname,
        "->",
        dns_lookup(hostname) or "NXDOMAIN / no simulated record",
    )


subsection("Real system DNS lookup")

try:
    resolved = socket.gethostbyname("localhost")
    print("localhost resolves to:", resolved)
except socket.gaierror as error:
    print("DNS resolution failed:", error)


# ============================================================================
# SECTION 9: ARP
# ============================================================================

section("ARP")

ARP_CACHE = {
    "192.168.1.1": "aa:aa:aa:aa:aa:01",
    "192.168.1.20": "aa:aa:aa:aa:aa:20",
}


def arp_lookup(ip_address: str) -> Optional[str]:
    ipaddress.IPv4Address(ip_address)
    return ARP_CACHE.get(ip_address)


for address in ["192.168.1.1", "192.168.1.20", "192.168.1.99"]:
    mac_address = arp_lookup(address)
    print(
        f"ARP {address:15} -> "
        f"{mac_address if mac_address else 'not present in cache'}"
    )

print(
    """
ARP is used in IPv4 Ethernet networks to discover the MAC address
associated with a local IPv4 address. IPv6 uses Neighbor Discovery
rather than ARP.
"""
)


# ============================================================================
# SECTION 10: ICMP
# ============================================================================

section("ICMP")

ICMP_TYPES = {
    0: "Echo Reply",
    3: "Destination Unreachable",
    5: "Redirect",
    8: "Echo Request",
    11: "Time Exceeded",
}


@dataclass
class ICMPMessage:
    message_type: int
    code: int
    payload: bytes = b""

    @property
    def description(self) -> str:
        return ICMP_TYPES.get(
            self.message_type,
            "Unknown ICMP type",
        )


ping_request = ICMPMessage(8, 0, b"network-test")
ping_reply = ICMPMessage(0, 0, b"network-test")

print("Request:", ping_request.description)
print("Reply  :", ping_reply.description)


# ============================================================================
# SECTION 11: ROUTING
# ============================================================================

section("ROUTING")

@dataclass
class Route:
    destination: ipaddress.IPv4Network
    next_hop: Optional[str]
    interface: str
    metric: int = 0

    def matches(self, address: ipaddress.IPv4Address) -> bool:
        return address in self.destination


class RoutingTable:
    """
    Simplified routing table.

    Real routers have considerably more complex routing systems,
    but the key principle demonstrated here is longest-prefix matching.
    """

    def __init__(self, routes: Iterable[Route]) -> None:
        self.routes = list(routes)

    def lookup(self, destination: str) -> Optional[Route]:
        address = ipaddress.IPv4Address(destination)
        matches = [
            route
            for route in self.routes
            if route.matches(address)
        ]

        if not matches:
            return None

        return max(
            matches,
            key=lambda route: (route.destination.prefixlen, -route.metric),
        )


routing_table = RoutingTable(
    [
        Route(
            ipaddress.ip_network("192.168.1.0/24"),
            None,
            "LAN",
        ),
        Route(
            ipaddress.ip_network("10.0.0.0/8"),
            "10.10.10.1",
            "WAN1",
        ),
        Route(
            ipaddress.ip_network("0.0.0.0/0"),
            "192.168.1.1",
            "LAN",
        ),
    ]
)

for destination in [
    "192.168.1.50",
    "10.20.30.40",
    "8.8.8.8",
]:
    route = routing_table.lookup(destination)
    if route:
        print(
            f"{destination:15} -> "
            f"{route.destination} via "
            f"{route.next_hop or 'direct'} on {route.interface}"
        )
    else:
        print(f"{destination:15} -> no route")


# ============================================================================
# SECTION 12: NETWORK DEVICES
# ============================================================================

section("NETWORK DEVICES")

devices = {
    "NIC": "Connects a host to a network.",
    "Hub": "Repeats incoming signals to connected ports.",
    "Switch": "Forwards Ethernet frames using MAC-address information.",
    "Router": "Forwards IP packets between networks.",
    "Access Point": "Connects wireless clients to a LAN.",
    "Modem": "Provides a physical/data connection to an access network.",
    "Firewall": "Allows or blocks traffic according to security rules.",
    "Load Balancer": "Distributes application traffic among backend systems.",
}

for name, purpose in devices.items():
    print(f"{name:16}: {purpose}")


# ============================================================================
# SECTION 13: NAT
# ============================================================================

section("NAT")

@dataclass
class NATEntry:
    internal_ip: str
    internal_port: int
    external_ip: str
    external_port: int
    destination_ip: str
    destination_port: int
    protocol: str


nat_table: list[NATEntry] = []


def create_nat_mapping(
    internal_ip: str,
    internal_port: int,
    external_ip: str,
    external_port: int,
    destination_ip: str,
    destination_port: int,
    protocol: str,
) -> NATEntry:
    entry = NATEntry(
        internal_ip,
        internal_port,
        external_ip,
        external_port,
        destination_ip,
        destination_port,
        protocol.upper(),
    )
    nat_table.append(entry)
    return entry


nat_entry = create_nat_mapping(
    "192.168.1.25",
    53142,
    "203.0.113.20",
    42001,
    "93.184.216.34",
    443,
    "TCP",
)

print(
    "Internal:",
    f"{nat_entry.internal_ip}:{nat_entry.internal_port}",
)
print(
    "Translated:",
    f"{nat_entry.external_ip}:{nat_entry.external_port}",
)
print(
    "Destination:",
    f"{nat_entry.destination_ip}:{nat_entry.destination_port}",
)


# ============================================================================
# SECTION 14: FIREWALL
# ============================================================================

section("FIREWALL")

@dataclass
class FirewallRule:
    source_network: ipaddress.IPv4Network
    destination_port: Optional[int]
    protocol: Optional[str]
    action: str
    description: str


class SimpleFirewall:
    """
    Educational firewall model.

    Production firewalls can inspect many more properties, maintain
    connection state, perform NAT, apply application-aware policies,
    and integrate with identity and security systems.
    """

    def __init__(self, rules: list[FirewallRule]) -> None:
        self.rules = rules

    def evaluate(
        self,
        source_ip: str,
        destination_port: int,
        protocol: str,
    ) -> tuple[str, str]:
        source = ipaddress.IPv4Address(source_ip)
        protocol = protocol.upper()

        for rule in self.rules:
            if source not in rule.source_network:
                continue

            if (
                rule.destination_port is not None
                and rule.destination_port != destination_port
            ):
                continue

            if (
                rule.protocol is not None
                and rule.protocol.upper() != protocol
            ):
                continue

            return rule.action, rule.description

        return "DENY", "Implicit deny"


firewall = SimpleFirewall(
    [
        FirewallRule(
            ipaddress.ip_network("192.168.1.0/24"),
            443,
            "TCP",
            "ALLOW",
            "Allow HTTPS from the LAN",
        ),
        FirewallRule(
            ipaddress.ip_network("192.168.1.0/24"),
            22,
            "TCP",
            "DENY",
            "Block SSH from the LAN",
        ),
    ]
)

tests = [
    ("192.168.1.25", 443, "TCP"),
    ("192.168.1.25", 22, "TCP"),
    ("192.168.1.25", 53, "UDP"),
]

for source, port, protocol in tests:
    action, reason = firewall.evaluate(source, port, protocol)
    print(
        f"{source} -> {protocol}/{port}: {action} ({reason})"
    )


# ============================================================================
# SECTION 15: PACKET REPRESENTATION
# ============================================================================

section("PACKET STRUCTURE")

@dataclass
class Packet:
    number: int
    timestamp: float
    source_mac: str
    destination_mac: str
    source_ip: str
    destination_ip: str
    transport_protocol: str
    source_port: Optional[int]
    destination_port: Optional[int]
    flags: Optional[int]
    payload: bytes
    application_protocol: Optional[str] = None
    info: str = ""

    @property
    def length(self) -> int:
        return len(self.payload)

    def summary(self) -> str:
        endpoint = (
            f"{self.source_ip}:{self.source_port} -> "
            f"{self.destination_ip}:{self.destination_port}"
            if self.source_port is not None
            else f"{self.source_ip} -> {self.destination_ip}"
        )

        flags = (
            f" [{flags_to_text(self.flags)}]"
            if self.flags is not None
            else ""
        )

        return (
            f"{self.number:3} "
            f"{self.transport_protocol:5} "
            f"{endpoint:45} "
            f"{self.application_protocol or '-':8}"
            f"{flags:20} "
            f"len={self.length:4} "
            f"{self.info}"
        )


now = time.time()

packets = [
    Packet(
        1,
        now,
        "00:11:22:33:44:55",
        "aa:bb:cc:dd:ee:ff",
        "192.168.1.25",
        "93.184.216.34",
        "TCP",
        53142,
        443,
        TCP_FLAGS["SYN"],
        b"",
        None,
        "SYN",
    ),
    Packet(
        2,
        now + 0.001,
        "aa:bb:cc:dd:ee:ff",
        "00:11:22:33:44:55",
        "93.184.216.34",
        "192.168.1.25",
        "TCP",
        443,
        53142,
        TCP_FLAGS["SYN"] | TCP_FLAGS["ACK"],
        b"",
        None,
        "SYN, ACK",
    ),
    Packet(
        3,
        now + 0.002,
        "00:11:22:33:44:55",
        "aa:bb:cc:dd:ee:ff",
        "192.168.1.25",
        "93.184.216.34",
        "TCP",
        53142,
        443,
        TCP_FLAGS["ACK"],
        b"",
        None,
        "ACK",
    ),
    Packet(
        4,
        now + 0.005,
        "00:11:22:33:44:55",
        "aa:bb:cc:dd:ee:ff",
        "192.168.1.25",
        "93.184.216.34",
        "TCP",
        53142,
        443,
        TCP_FLAGS["ACK"] | TCP_FLAGS["PSH"],
        b"GET / HTTP/1.1\r\nHost: example.test\r\n\r\n",
        "HTTP",
        "HTTP GET /",
    ),
    Packet(
        5,
        now + 0.030,
        "00:11:22:33:44:55",
        "aa:bb:cc:dd:ee:ff",
        "192.168.1.25",
        "8.8.8.8",
        "UDP",
        53000,
        53,
        None,
        b"example.test",
        "DNS",
        "DNS query",
    ),
    Packet(
        6,
        now + 0.040,
        "00:11:22:33:44:55",
        "aa:bb:cc:dd:ee:ff",
        "192.168.1.25",
        "1.1.1.1",
        "ICMP",
        None,
        None,
        None,
        b"ping",
        "ICMP",
        "Echo request",
    ),
]

print(
    "No. Proto Source/Destination                                "
    "App      Flags                Length Info"
)
print("-" * 120)
for packet in packets:
    print(packet.summary())


# ============================================================================
# SECTION 16: PACKET ANALYSIS
# ============================================================================

section("PACKET ANALYSIS")

protocol_counts = Counter(packet.transport_protocol for packet in packets)
application_counts = Counter(
    packet.application_protocol
    for packet in packets
    if packet.application_protocol
)
source_counts = Counter(packet.source_ip for packet in packets)
destination_counts = Counter(packet.destination_ip for packet in packets)

print("Transport protocol counts:")
for protocol, count in protocol_counts.items():
    print(f"  {protocol}: {count}")

print("\nApplication protocol counts:")
for protocol, count in application_counts.items():
    print(f"  {protocol}: {count}")

print("\nTop source IPs:")
for address, count in source_counts.most_common():
    print(f"  {address}: {count}")

print("\nTop destination IPs:")
for address, count in destination_counts.most_common():
    print(f"  {address}: {count}")


def filter_packets(
    packets_to_filter: Iterable[Packet],
    *,
    protocol: Optional[str] = None,
    source: Optional[str] = None,
    destination: Optional[str] = None,
    port: Optional[int] = None,
    application: Optional[str] = None,
) -> list[Packet]:
    """
    A simplified equivalent of the logical idea behind Wireshark
    display filtering.

    Examples conceptually resemble:
        tcp
        ip.addr == 192.168.1.25
        tcp.port == 443
        dns
    """
    result = []

    for packet in packets_to_filter:
        if (
            protocol is not None
            and packet.transport_protocol.upper() != protocol.upper()
        ):
            continue

        if source is not None and packet.source_ip != source:
            continue

        if destination is not None and packet.destination_ip != destination:
            continue

        if port is not None:
            if (
                packet.source_port != port
                and packet.destination_port != port
            ):
                continue

        if application is not None:
            if (
                packet.application_protocol is None
                or packet.application_protocol.upper()
                != application.upper()
            ):
                continue

        result.append(packet)

    return result


print("\nPackets matching TCP:")
for packet in filter_packets(packets, protocol="TCP"):
    print(" ", packet.summary())

print("\nPackets involving port 443:")
for packet in filter_packets(packets, port=443):
    print(" ", packet.summary())

print("\nPackets with application protocol DNS:")
for packet in filter_packets(packets, application="DNS"):
    print(" ", packet.summary())


# ============================================================================
# SECTION 17: WIRESHARK CONCEPTS
# ============================================================================

section("WIRESHARK CONCEPTS")

wireshark_filter_examples = {
    "tcp": "Show TCP packets.",
    "udp": "Show UDP packets.",
    "dns": "Show DNS packets.",
    "http": "Show packets recognized as HTTP.",
    "icmp": "Show ICMP packets.",
    "ip.addr == 192.168.1.25":
        "Show IP packets where either endpoint is 192.168.1.25.",
    "ip.src == 192.168.1.25":
        "Show packets whose source IP is 192.168.1.25.",
    "ip.dst == 8.8.8.8":
        "Show packets whose destination IP is 8.8.8.8.",
    "tcp.port == 443":
        "Show TCP packets using port 443 at either endpoint.",
    "tcp.flags.syn == 1":
        "Show TCP packets with the SYN flag set.",
    "tcp.flags.reset == 1":
        "Show TCP reset packets.",
    "tcp.stream == 0":
        "Show packets belonging to one TCP stream.",
    "dns.qry.name == \"example.test\"":
        "Show DNS queries for example.test.",
    "tcp && ip.addr == 192.168.1.25":
        "Combine protocol and address conditions.",
}

for expression, meaning in wireshark_filter_examples.items():
    print(f"{expression:42} -> {meaning}")


subsection("Capture filters versus display filters")

print(
    """
A capture filter controls what traffic is captured or retained by the
capture mechanism. It is useful when reducing traffic volume before
analysis.

A display filter is applied after packets are available to the analyzer.
It changes which packets are shown without changing the captured data.

This distinction matters because filtering too aggressively during
capture can permanently remove packets that might later prove useful.
"""
)


# ============================================================================
# SECTION 18: TCP CONVERSATION RECONSTRUCTION
# ============================================================================

section("TCP CONVERSATION ANALYSIS")

tcp_packets = [
    packet
    for packet in packets
    if packet.transport_protocol == "TCP"
    and packet.source_port is not None
]

streams: dict[tuple, list[Packet]] = defaultdict(list)

for packet in tcp_packets:
    endpoint_a = (packet.source_ip, packet.source_port)
    endpoint_b = (packet.destination_ip, packet.destination_port)
    key = tuple(sorted((endpoint_a, endpoint_b)))
    streams[key].append(packet)

for stream_key, stream_packets in streams.items():
    print("\nTCP conversation:", stream_key)
    for packet in sorted(stream_packets, key=lambda item: item.timestamp):
        print(
            f"  #{packet.number}: {packet.source_ip}:{packet.source_port}"
            f" -> {packet.destination_ip}:{packet.destination_port}"
            f" {packet.info}"
        )


# ============================================================================
# SECTION 19: LATENCY
# ============================================================================

section("LATENCY AND TIMING")

def packet_deltas(packet_list: list[Packet]) -> list[float]:
    ordered = sorted(packet_list, key=lambda packet: packet.timestamp)
    return [
        ordered[index].timestamp - ordered[index - 1].timestamp
        for index in range(1, len(ordered))
    ]


deltas = packet_deltas(packets)

if deltas:
    print("Inter-packet delays:")
    for delta in deltas:
        print(f"  {delta * 1000:.3f} ms")

    print(f"Minimum: {min(deltas) * 1000:.3f} ms")
    print(f"Maximum: {max(deltas) * 1000:.3f} ms")
    print(f"Average: {sum(deltas) / len(deltas) * 1000:.3f} ms")


# ============================================================================
# SECTION 20: PACKET LOSS SIMULATION
# ============================================================================

section("PACKET LOSS SIMULATION")

def simulate_packet_delivery(
    packet_count: int,
    loss_probability: float,
    seed: int = 7,
) -> tuple[list[int], list[int]]:
    """
    Demonstrates that packet loss can be modeled independently from
    the application data itself.

    TCP can detect missing sequence progress and retransmit.
    UDP does not automatically provide retransmission at the transport layer.
    """
    if not 0 <= loss_probability <= 1:
        raise ValueError("Loss probability must be between 0 and 1.")

    random_generator = random.Random(seed)

    delivered = []
    lost = []

    for sequence in range(1, packet_count + 1):
        if random_generator.random() < loss_probability:
            lost.append(sequence)
        else:
            delivered.append(sequence)

    return delivered, lost


delivered, lost = simulate_packet_delivery(20, 0.20)

print("Delivered:", delivered)
print("Lost     :", lost)
print(f"Delivery ratio: {len(delivered) / 20:.1%}")


# ============================================================================
# SECTION 21: CHECKSUM CONCEPT
# ============================================================================

section("CHECKSUM CONCEPT")

def internet_checksum(data: bytes) -> int:
    """
    Compute the standard one's-complement Internet checksum algorithm
    used by several Internet protocols.

    This implementation pads odd-length input with one zero byte.
    """
    if len(data) % 2:
        data += b"\x00"

    total = 0

    for index in range(0, len(data), 2):
        word = (data[index] << 8) | data[index + 1]
        total += word
        total = (total & 0xFFFF) + (total >> 16)

    return (~total) & 0xFFFF


for payload in [
    b"",
    b"hello",
    b"network packet",
]:
    checksum = internet_checksum(payload)
    print(
        f"{payload!r:20} checksum=0x{checksum:04x}"
    )


# ============================================================================
# SECTION 22: IPv4 HEADER CONSTRUCTION
# ============================================================================

section("BUILDING A SIMPLIFIED IPv4 HEADER")

def ipv4_header_demo(
    source: str,
    destination: str,
    protocol_number: int,
    payload_length: int,
    identification: int = 1,
) -> bytes:
    """
    Build an IPv4 header without options.

    Header fields:

        Version + IHL
        DSCP/ECN
        Total length
        Identification
        Flags + Fragment Offset
        TTL
        Protocol
        Header checksum
        Source address
        Destination address

    The checksum is calculated after constructing the header with a
    zero checksum field.
    """
    source_bytes = ipaddress.IPv4Address(source).packed
    destination_bytes = ipaddress.IPv4Address(destination).packed

    version = 4
    ihl = 5
    version_ihl = (version << 4) | ihl

    dscp_ecn = 0
    total_length = 20 + payload_length
    flags_fragment_offset = 0
    ttl = 64

    header_without_checksum = struct.pack(
        "!BBHHHBBH4s4s",
        version_ihl,
        dscp_ecn,
        total_length,
        identification,
        flags_fragment_offset,
        ttl,
        protocol_number,
        0,
        source_bytes,
        destination_bytes,
    )

    checksum = internet_checksum(header_without_checksum)

    return struct.pack(
        "!BBHHHBBH4s4s",
        version_ihl,
        dscp_ecn,
        total_length,
        identification,
        flags_fragment_offset,
        ttl,
        protocol_number,
        checksum,
        source_bytes,
        destination_bytes,
    )


ipv4_header = ipv4_header_demo(
    "192.168.1.25",
    "93.184.216.34",
    protocol_number=6,
    payload_length=40,
)

print("IPv4 header length:", len(ipv4_header))
print("IPv4 header hex   :", ipv4_header.hex())
print("Checksum          :", f"0x{struct.unpack('!H', ipv4_header[10:12])[0]:04x}")


# ============================================================================
# SECTION 23: WIRESHARK-LIKE PACKET DISSECTION
# ============================================================================

section("PACKET DISSECTION")

def dissect_packet(packet: Packet) -> None:
    print(f"Frame {packet.number}")
    print(f"  Timestamp       : {packet.timestamp:.6f}")
    print(f"  Frame length    : {packet.length} payload bytes")

    print("\nEthernet II")
    print(f"  Source          : {packet.source_mac}")
    print(f"  Destination     : {packet.destination_mac}")

    print("\nInternet Protocol")
    print(f"  Source          : {packet.source_ip}")
    print(f"  Destination     : {packet.destination_ip}")
    print(f"  Protocol        : {packet.transport_protocol}")

    if packet.source_port is not None:
        print(f"\n{packet.transport_protocol}")
        print(f"  Source port     : {packet.source_port}")
        print(f"  Destination port: {packet.destination_port}")

    if packet.flags is not None:
        print(f"  Flags           : {flags_to_text(packet.flags)}")

    if packet.application_protocol:
        print(f"\nApplication")
        print(f"  Protocol        : {packet.application_protocol}")

    if packet.payload:
        printable = packet.payload[:80].decode(
            "utf-8",
            errors="replace",
        )
        print(f"  Payload preview : {printable!r}")


dissect_packet(packets[3])


# ============================================================================
# SECTION 24: TROUBLESHOOTING
# ============================================================================

section("NETWORK TROUBLESHOOTING MODEL")

troubleshooting_steps = [
    (
        "1. Physical/link",
        "Check cable, Wi-Fi association, NIC state, link status.",
    ),
    (
        "2. Local addressing",
        "Check IP address, subnet mask/prefix and default gateway.",
    ),
    (
        "3. Local reachability",
        "Check whether the host can reach its gateway.",
    ),
    (
        "4. Name resolution",
        "Determine whether DNS is resolving the expected address.",
    ),
    (
        "5. Routing",
        "Inspect the route toward the destination.",
    ),
    (
        "6. Transport",
        "Check whether TCP/UDP traffic reaches the expected port.",
    ),
    (
        "7. Application",
        "Inspect application protocol requests and responses.",
    ),
    (
        "8. Security",
        "Check firewall, ACL, authentication and encryption behavior.",
    ),
]

for step, explanation in troubleshooting_steps:
    print(f"{step:20} -> {explanation}")


# ============================================================================
# SECTION 25: COMMON FAILURE PATTERNS
# ============================================================================

section("COMMON FAILURE PATTERNS")

failure_patterns = {
    "No link": [
        "NIC disabled",
        "Cable or wireless problem",
        "Switch port issue",
    ],
    "Wrong IP configuration": [
        "Incorrect subnet",
        "Duplicate address",
        "Missing default gateway",
    ],
    "DNS failure": [
        "DNS server unreachable",
        "Incorrect record",
        "Search-domain configuration issue",
    ],
    "TCP connection failure": [
        "No service listening",
        "Firewall rejection",
        "Routing problem",
        "Server unavailable",
    ],
    "Slow application": [
        "High latency",
        "Packet loss",
        "Retransmissions",
        "Server processing delay",
        "Congestion",
    ],
}

for failure, possibilities in failure_patterns.items():
    print(f"\n{failure}")
    for possibility in possibilities:
        print(f"  - {possibility}")


# ============================================================================
# SECTION 26: SECURITY CONSIDERATIONS
# ============================================================================

section("NETWORK SECURITY")

print(
    """
Important security principles:

1. Confidentiality
   Encryption prevents unauthorized parties from reading protected data.

2. Integrity
   Cryptographic mechanisms can detect unauthorized modification.

3. Authentication
   Systems verify the identity of users, devices or services.

4. Authorization
   Access is restricted according to defined permissions.

5. Segmentation
   Dividing networks can reduce the impact of compromise.

6. Least privilege
   Services should expose only the access they actually require.

7. Monitoring
   Packet and connection metadata can reveal failures and suspicious
   behavior.

8. TLS
   HTTPS commonly uses TLS to protect HTTP communication in transit.

9. Sensitive captures
   Packet captures can contain credentials, cookies, personal data,
   internal addresses and application content. Captures must therefore
   be handled as potentially sensitive data.
"""
)


# ============================================================================
# SECTION 27: PERFORMANCE CONSIDERATIONS
# ============================================================================

section("PERFORMANCE")

@dataclass
class PerformanceMeasurement:
    bytes_transferred: int
    elapsed_seconds: float

    @property
    def bits_per_second(self) -> float:
        if self.elapsed_seconds <= 0:
            return float("inf")
        return (self.bytes_transferred * 8) / self.elapsed_seconds

    @property
    def megabits_per_second(self) -> float:
        return self.bits_per_second / 1_000_000


measurement = PerformanceMeasurement(
    bytes_transferred=125_000_000,
    elapsed_seconds=10,
)

print("Transferred bytes:", measurement.bytes_transferred)
print("Elapsed seconds  :", measurement.elapsed_seconds)
print("Throughput       :", f"{measurement.megabits_per_second:.2f} Mbps")


# ============================================================================
# SECTION 28: SIMPLE PACKET CAPTURE ANALYZER
# ============================================================================

section("PACKET CAPTURE ANALYZER")

class PacketAnalyzer:
    def __init__(self, packets_to_analyze: list[Packet]) -> None:
        self.packets = packets_to_analyze

    def protocol_distribution(self) -> Counter:
        return Counter(
            packet.transport_protocol
            for packet in self.packets
        )

    def top_talkers(self, limit: int = 5) -> list[tuple[str, int]]:
        counts = Counter()
        for packet in self.packets:
            counts[packet.source_ip] += packet.length
            counts[packet.destination_ip] += packet.length
        return counts.most_common(limit)

    def conversations(self) -> dict[tuple, int]:
        result: Counter = Counter()

        for packet in self.packets:
            left = (packet.source_ip, packet.source_port)
            right = (packet.destination_ip, packet.destination_port)

            if left <= right:
                key = (left, right)
            else:
                key = (right, left)

            result[key] += packet.length

        return dict(result)

    def find_large_payloads(self, minimum: int) -> list[Packet]:
        return [
            packet
            for packet in self.packets
            if packet.length >= minimum
        ]


analyzer = PacketAnalyzer(packets)

print("Protocol distribution:", dict(analyzer.protocol_distribution()))

print("\nTop talkers by observed payload bytes:")
for address, byte_count in analyzer.top_talkers():
    print(f"  {address:15} {byte_count:6} bytes")

print("\nConversations:")
for conversation, byte_count in analyzer.conversations().items():
    print(f"  {conversation} -> {byte_count} bytes")

print("\nPackets with payload >= 20 bytes:")
for packet in analyzer.find_large_payloads(20):
    print(f"  Packet {packet.number}: {packet.length} bytes")


# ============================================================================
# SECTION 29: EDGE CASES AND VALIDATION
# ============================================================================

section("EDGE CASES AND VALIDATION")

def validate_port(value: int) -> bool:
    return isinstance(value, int) and 0 <= value <= 65535


def validate_ipv4(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).version == 4
    except ValueError:
        return False


validation_values = [
    ("port 0", validate_port(0)),
    ("port 443", validate_port(443)),
    ("port 65535", validate_port(65535)),
    ("port 65536", validate_port(65536)),
    ("IPv4 192.168.1.1", validate_ipv4("192.168.1.1")),
    ("IPv4 999.1.1.1", validate_ipv4("999.1.1.1")),
    ("IPv4 text", validate_ipv4("hello")),
]

for description, result in validation_values:
    print(f"{description:25}: {result}")


# ============================================================================
# SECTION 30: SOCKET API DEMONSTRATION
# ============================================================================

section("PYTHON SOCKET API")

print(
    """
Python's socket module provides operating-system networking interfaces.

Common socket concepts:

  socket.AF_INET       IPv4
  socket.AF_INET6      IPv6
  socket.SOCK_STREAM   TCP-style stream socket
  socket.SOCK_DGRAM    UDP-style datagram socket

The following example creates a TCP socket object without making an
external connection.
"""
)

tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

try:
    print("Socket family :", tcp_socket.family)
    print("Socket type   :", tcp_socket.type)
    print("Socket proto  :", tcp_socket.proto)
finally:
    tcp_socket.close()


# ============================================================================
# SECTION 31: APPLICATION PROTOCOL EXAMPLE
# ============================================================================

section("HTTP REQUEST STRUCTURE")

http_request = (
    "GET /index.html HTTP/1.1\r\n"
    "Host: example.test\r\n"
    "Accept: text/html\r\n"
    "Connection: close\r\n"
    "\r\n"
)

print(http_request)

print(
    """
An HTTP request contains:

  Method       GET
  Request path /index.html
  HTTP version HTTP/1.1
  Headers      Host, Accept, Connection
  Empty line   Separates headers from the optional body

When HTTP is transported over TCP, a packet analyzer can observe
TCP-level behavior and, when the traffic is not encrypted, may also
interpret HTTP fields.
"""
)


# ============================================================================
# SECTION 32: HTTPS AND ENCRYPTION
# ============================================================================

section("HTTPS")

print(
    """
HTTPS is HTTP carried through a TLS-protected connection.

A packet capture can still reveal useful metadata such as:

  - IP addresses
  - TCP or UDP transport information, depending on the protocol
  - Ports
  - Packet sizes
  - Timing
  - Connection setup behavior

Encryption prevents ordinary passive observation from directly reading
protected application payloads.

Modern web traffic may also use HTTP/3 over QUIC, which runs over UDP
rather than traditional HTTP-over-TCP.
"""
)


# ============================================================================
# SECTION 33: TCP STATE MACHINE
# ============================================================================

section("TCP STATE MACHINE")

tcp_states = [
    "CLOSED",
    "LISTEN",
    "SYN-SENT",
    "SYN-RECEIVED",
    "ESTABLISHED",
    "FIN-WAIT-1",
    "FIN-WAIT-2",
    "CLOSE-WAIT",
    "LAST-ACK",
    "TIME-WAIT",
]

for index, state in enumerate(tcp_states, start=1):
    print(f"{index:2}. {state}")

print(
    """
A packet capture can help identify where a TCP connection stops.

For example:

  SYN with no response
      -> possible routing, filtering, server availability or address issue

  SYN followed by RST
      -> endpoint or intermediate system actively rejected/reset it

  Successful handshake but no application response
      -> investigate application behavior, server processing, filtering,
         protocol negotiation or payload handling
"""
)


# ============================================================================
# SECTION 34: MTU AND FRAGMENTATION CONCEPT
# ============================================================================

section("MTU")

@dataclass
class MTUResult:
    payload_size: int
    mtu: int
    requires_fragmentation: bool


def check_mtu(payload_size: int, mtu: int = 1500) -> MTUResult:
    if payload_size < 0:
        raise ValueError("Payload size cannot be negative.")

    return MTUResult(
        payload_size,
        mtu,
        payload_size + 20 > mtu,
    )


for size in [100, 1400, 1480, 1500, 2000]:
    result = check_mtu(size)
    print(
        f"Payload {size:4} bytes, MTU {result.mtu}: "
        f"fragmentation/oversize consideration="
        f"{result.requires_fragmentation}"
    )


# ============================================================================
# SECTION 35: WIRESHARK ANALYSIS WORKFLOW
# ============================================================================

section("WIRESHARK ANALYSIS WORKFLOW")

workflow = [
    "Start with the capture scope and question.",
    "Identify the relevant hosts and time interval.",
    "Inspect packet numbers, timestamps and lengths.",
    "Identify Ethernet or Wi-Fi information where available.",
    "Inspect IP addresses and protocol fields.",
    "Inspect TCP/UDP ports and connection behavior.",
    "Follow DNS activity when names are involved.",
    "Follow TCP streams when reconstructing a conversation.",
    "Inspect retransmissions, resets and duplicate acknowledgements.",
    "Compare request and response timing.",
    "Use filters to isolate the relevant traffic.",
    "Check whether encryption changes what payload information is visible.",
    "Correlate packet evidence with host and application observations.",
]

for index, item in enumerate(workflow, start=1):
    print(f"{index:2}. {item}")


# ============================================================================
# SECTION 36: FILTER PARSER
# ============================================================================

section("SIMPLIFIED WIRESHARK-STYLE FILTER ENGINE")

def parse_simple_filter(expression: str):
    """
    Educational parser for a small subset of Wireshark-like filters.

    Supported expressions:

        tcp
        udp
        dns
        http
        tcp.port == 443
        ip.src == 192.168.1.25
        ip.dst == 8.8.8.8
        ip.addr == 192.168.1.25
    """
    expression = expression.strip()

    if expression.lower() in {"tcp", "udp", "dns", "http", "icmp"}:
        return ("protocol", expression.lower())

    parts = expression.split()

    if len(parts) == 3 and parts[1] == "==":
        field_name = parts[0]
        value = parts[2].strip('"')

        if field_name in {
            "tcp.port",
            "ip.src",
            "ip.dst",
            "ip.addr",
            "dns.qry.name",
        }:
            return ("comparison", field_name, value)

    raise ValueError(f"Unsupported filter: {expression}")


def apply_simple_filter(
    packet_list: list[Packet],
    expression: str,
) -> list[Packet]:
    parsed = parse_simple_filter(expression)

    if parsed[0] == "protocol":
        protocol = parsed[1]

        if protocol in {"tcp", "udp", "icmp"}:
            return [
                packet
                for packet in packet_list
                if packet.transport_protocol.lower() == protocol
            ]

        return [
            packet
            for packet in packet_list
            if (
                packet.application_protocol
                and packet.application_protocol.lower() == protocol
            )
        ]

    _, field_name, value = parsed

    if field_name == "tcp.port":
        port = int(value)
        return filter_packets(packet_list, port=port)

    if field_name == "ip.src":
        return filter_packets(packet_list, source=value)

    if field_name == "ip.dst":
        return filter_packets(packet_list, destination=value)

    if field_name == "ip.addr":
        return [
            packet
            for packet in packet_list
            if packet.source_ip == value
            or packet.destination_ip == value
        ]

    if field_name == "dns.qry.name":
        return [
            packet
            for packet in packet_list
            if (
                packet.application_protocol == "DNS"
                and packet.payload.decode(
                    "utf-8",
                    errors="ignore",
                ) == value
            )
        ]

    return []


for expression in [
    "tcp",
    "udp",
    "tcp.port == 443",
    "ip.addr == 192.168.1.25",
]:
    print(f"\nFilter: {expression}")
    try:
        matches = apply_simple_filter(packets, expression)
        for packet in matches:
            print(" ", packet.summary())
    except ValueError as error:
        print(" ", error)


# ============================================================================
# SECTION 37: PACKET RATE AND BANDWIDTH
# ============================================================================

section("PACKET RATE AND BANDWIDTH")

def traffic_statistics(packet_list: list[Packet]) -> dict[str, float]:
    if len(packet_list) < 2:
        return {
            "packets": float(len(packet_list)),
            "bytes": float(sum(p.length for p in packet_list)),
            "duration": 0.0,
            "packets_per_second": 0.0,
            "bytes_per_second": 0.0,
            "bits_per_second": 0.0,
        }

    ordered = sorted(packet_list, key=lambda packet: packet.timestamp)
    duration = ordered[-1].timestamp - ordered[0].timestamp
    total_bytes = sum(packet.length for packet in packet_list)

    if duration <= 0:
        return {
            "packets": float(len(packet_list)),
            "bytes": float(total_bytes),
            "duration": duration,
            "packets_per_second": float("inf"),
            "bytes_per_second": float("inf"),
            "bits_per_second": float("inf"),
        }

    return {
        "packets": float(len(packet_list)),
        "bytes": float(total_bytes),
        "duration": duration,
        "packets_per_second": len(packet_list) / duration,
        "bytes_per_second": total_bytes / duration,
        "bits_per_second": total_bytes * 8 / duration,
    }


stats = traffic_statistics(packets)

for key, value in stats.items():
    if "per_second" in key:
        print(f"{key:20}: {value:.2f}")
    else:
        print(f"{key:20}: {value:.6f}")


# ============================================================================
# SECTION 38: TESTS
# ============================================================================

section("SELF-TESTS")

def run_tests() -> None:
    assert normalize_mac("AABBCCDDEEFF") == "aa:bb:cc:dd:ee:ff"

    assert validate_port(0)
    assert validate_port(65535)
    assert not validate_port(65536)

    assert validate_ipv4("127.0.0.1")
    assert not validate_ipv4("300.1.1.1")

    assert same_subnet(
        "192.168.1.10",
        "192.168.1.20",
        24,
    )

    assert not same_subnet(
        "192.168.1.10",
        "192.168.2.20",
        24,
    )

    assert dns_lookup("example.test") == "192.0.2.10"
    assert dns_lookup("missing.test") is None

    route = routing_table.lookup("8.8.8.8")
    assert route is not None
    assert route.destination == ipaddress.ip_network("0.0.0.0/0")

    assert firewall.evaluate(
        "192.168.1.25",
        443,
        "TCP",
    )[0] == "ALLOW"

    assert firewall.evaluate(
        "192.168.1.25",
        22,
        "TCP",
    )[0] == "DENY"

    handshake = simulate_tcp_handshake()
    assert handshake[0].flags & TCP_FLAGS["SYN"]
    assert handshake[1].flags & TCP_FLAGS["SYN"]
    assert handshake[1].flags & TCP_FLAGS["ACK"]
    assert handshake[2].flags & TCP_FLAGS["ACK"]

    assert len(ipv4_header) == 20
    assert internet_checksum(b"") == 0xFFFF

    print("All self-tests passed.")


run_tests()


# ============================================================================
# SECTION 39: PRACTICAL ANALYSIS QUESTIONS
# ============================================================================

section("PRACTICAL ANALYSIS QUESTIONS")

questions = [
    "Which IP address initiated the TCP connection?",
    "Which destination port identifies the server service?",
    "Which packets form the TCP three-way handshake?",
    "What sequence and acknowledgement numbers appear during setup?",
    "Which packet contains an HTTP request?",
    "Which traffic uses UDP port 53?",
    "Which traffic is ICMP?",
    "Which addresses are local/private addresses?",
    "Which route would a router choose for 8.8.8.8?",
    "What evidence would indicate a TCP reset?",
    "What evidence would suggest retransmission or packet loss?",
    "Which information can remain visible even when application payloads are encrypted?",
]

for question in questions:
    print("?", question)


# ============================================================================
# SECTION 40: FINAL REFERENCE TABLE
# ============================================================================

section("QUICK REFERENCE")

reference = [
    ("Ethernet", "Link", "Frames and MAC addresses"),
    ("ARP", "Link/Network boundary", "IPv4-to-MAC resolution on local networks"),
    ("IP", "Internet", "Logical addressing and packet delivery"),
    ("ICMP", "Internet", "Control and diagnostic messaging"),
    ("TCP", "Transport", "Reliable ordered byte stream"),
    ("UDP", "Transport", "Connectionless datagrams"),
    ("DNS", "Application", "Names to network information"),
    ("DHCP", "Application", "Automatic IP configuration"),
    ("HTTP", "Application", "Web application protocol"),
    ("HTTPS", "Application/Security", "HTTP protected by TLS"),
    ("SSH", "Application", "Secure remote administration"),
    ("Wireshark", "Analysis tool", "Interactive packet capture and analysis"),
]

for technology, layer, purpose in reference:
    print(f"{technology:12} | {layer:20} | {purpose}")


print(
    """
The central analytical model is:

    Application
        ↓
    Transport
        ↓
    Internet
        ↓
    Link
        ↓
    Physical transmission

A packet analyzer allows these layers to be inspected as observed
network traffic. Effective analysis connects individual packet fields
to the behavior of the complete communication.
"""
)
