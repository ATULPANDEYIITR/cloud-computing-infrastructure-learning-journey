"""
TCP/IP MODEL
============

A comprehensive standalone study and demonstration program covering:

1. Network Access Layer
2. Internet Layer
3. Transport Layer
4. Application Layer
5. Protocol mapping
6. Encapsulation and decapsulation
7. Addressing
8. TCP and UDP
9. IP and routing concepts
10. ARP, Ethernet, DNS, HTTP, HTTPS, DHCP, ICMP, SSH and related protocols
11. Packet construction and parsing
12. Checksums
13. TCP connection establishment
14. Reliable delivery concepts
15. Fragmentation and MTU
16. Ports and sockets
17. NAT and private addressing
18. Subnetting
19. Error handling
20. Security considerations
21. Performance and troubleshooting

The program uses only Python's standard library.
It intentionally models important networking mechanisms rather than
depending on external packet-capture libraries.

The demonstrations are educational simulations. They do not attempt
to reproduce every byte or implementation detail of a production
network stack.
"""

from __future__ import annotations

import hashlib
import ipaddress
import random
import socket
import struct
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 1. FUNDAMENTAL TCP/IP MODEL
# ---------------------------------------------------------------------------

class Layer(Enum):
    """The four layers of the commonly taught TCP/IP model."""

    NETWORK_ACCESS = 1
    INTERNET = 2
    TRANSPORT = 3
    APPLICATION = 4


LAYER_DESCRIPTIONS = {
    Layer.NETWORK_ACCESS: (
        "Moves frames across the local network medium. "
        "Typical technologies include Ethernet and Wi-Fi."
    ),
    Layer.INTERNET: (
        "Provides logical addressing and routing between networks. "
        "IPv4, IPv6 and ICMP operate here."
    ),
    Layer.TRANSPORT: (
        "Provides process-to-process communication using ports. "
        "TCP and UDP are the principal protocols."
    ),
    Layer.APPLICATION: (
        "Provides application-level network services such as DNS, HTTP, "
        "HTTPS, DHCP and SSH."
    ),
}


PROTOCOL_MAPPING = {
    "Ethernet": Layer.NETWORK_ACCESS,
    "Wi-Fi": Layer.NETWORK_ACCESS,
    "ARP": Layer.NETWORK_ACCESS,
    "IPv4": Layer.INTERNET,
    "IPv6": Layer.INTERNET,
    "ICMP": Layer.INTERNET,
    "TCP": Layer.TRANSPORT,
    "UDP": Layer.TRANSPORT,
    "DNS": Layer.APPLICATION,
    "HTTP": Layer.APPLICATION,
    "HTTPS": Layer.APPLICATION,
    "DHCP": Layer.APPLICATION,
    "SSH": Layer.APPLICATION,
    "SMTP": Layer.APPLICATION,
    "IMAP": Layer.APPLICATION,
}


def print_model() -> None:
    """Display the four TCP/IP layers from bottom to top."""

    print("\nTCP/IP MODEL")
    print("-" * 72)

    for layer in sorted(Layer, key=lambda item: item.value):
        print(f"{layer.value}. {layer.name.replace('_', ' ').title()}")
        print(f"   {LAYER_DESCRIPTIONS[layer]}")

    print("\nCommon protocol mapping:")
    for protocol, layer in PROTOCOL_MAPPING.items():
        print(f"  {protocol:<10} -> {layer.name.replace('_', ' ').title()}")


# ---------------------------------------------------------------------------
# 2. ENCAPSULATION AND DECAPSULATION
# ---------------------------------------------------------------------------

@dataclass
class ApplicationData:
    """Data produced by an application."""

    protocol: str
    payload: bytes


@dataclass
class TransportSegment:
    """A simplified TCP/UDP transport data unit."""

    protocol: str
    source_port: int
    destination_port: int
    payload: bytes
    sequence_number: Optional[int] = None
    acknowledgment_number: Optional[int] = None


@dataclass
class InternetPacket:
    """A simplified IP packet."""

    protocol: str
    source_ip: str
    destination_ip: str
    payload: object
    ttl: int = 64


@dataclass
class NetworkFrame:
    """A simplified Ethernet/Wi-Fi-like frame."""

    technology: str
    source_mac: str
    destination_mac: str
    payload: object


def demonstrate_encapsulation() -> None:
    """
    Demonstrate the conceptual direction:

    Application data
        -> TCP segment
        -> IP packet
        -> Ethernet frame

    Each lower layer adds information needed by that layer.
    """

    print("\nENCAPSULATION")
    print("-" * 72)

    application = ApplicationData(
        protocol="HTTP",
        payload=b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n",
    )

    transport = TransportSegment(
        protocol="TCP",
        source_port=51500,
        destination_port=80,
        payload=application.payload,
        sequence_number=1000,
    )

    internet = InternetPacket(
        protocol="IPv4/TCP",
        source_ip="192.168.1.10",
        destination_ip="93.184.216.34",
        payload=transport,
    )

    frame = NetworkFrame(
        technology="Ethernet",
        source_mac="02:00:00:00:00:10",
        destination_mac="02:00:00:00:00:01",
        payload=internet,
    )

    print(f"Application data: {application.protocol}")
    print(f"  Payload bytes: {len(application.payload)}")
    print(
        f"Transport: {transport.protocol}, "
        f"{transport.source_port} -> {transport.destination_port}"
    )
    print(
        f"Internet: {internet.source_ip} -> {internet.destination_ip}, "
        f"TTL={internet.ttl}"
    )
    print(
        f"Network access: {frame.technology}, "
        f"{frame.source_mac} -> {frame.destination_mac}"
    )

    print("\nDecapsulation reverses the process:")
    print("  Frame -> IP packet -> TCP segment -> Application data")


# ---------------------------------------------------------------------------
# 3. MAC ADDRESSING
# ---------------------------------------------------------------------------

def normalize_mac(mac: str) -> str:
    """Validate and normalize a MAC address."""

    cleaned = mac.replace("-", ":").lower()
    parts = cleaned.split(":")

    if len(parts) != 6 or any(len(part) != 2 for part in parts):
        raise ValueError(f"Invalid MAC address: {mac}")

    try:
        values = [int(part, 16) for part in parts]
    except ValueError as exc:
        raise ValueError(f"Invalid hexadecimal MAC address: {mac}") from exc

    if any(value < 0 or value > 255 for value in values):
        raise ValueError(f"Invalid MAC address: {mac}")

    return ":".join(f"{value:02x}" for value in values)


def demonstrate_mac_addresses() -> None:
    print("\nMAC ADDRESSING")
    print("-" * 72)

    addresses = [
        "00:1A:2B:3C:4D:5E",
        "AA-BB-CC-DD-EE-FF",
    ]

    for address in addresses:
        print(f"{address} -> {normalize_mac(address)}")

    for address in ["invalid", "00:11:22:33:44"]:
        try:
            normalize_mac(address)
        except ValueError as exc:
            print(f"Rejected {address!r}: {exc}")


# ---------------------------------------------------------------------------
# 4. IPV4 ADDRESSING
# ---------------------------------------------------------------------------

def demonstrate_ipv4() -> None:
    print("\nIPv4 ADDRESSING")
    print("-" * 72)

    addresses = [
        "127.0.0.1",
        "192.168.1.10",
        "10.20.30.40",
        "8.8.8.8",
    ]

    for address in addresses:
        ip = ipaddress.ip_address(address)

        print(
            f"{ip} | version={ip.version} | "
            f"private={ip.is_private} | loopback={ip.is_loopback}"
        )

    invalid_addresses = [
        "999.1.1.1",
        "192.168.1.999",
        "hello",
    ]

    for address in invalid_addresses:
        try:
            ipaddress.ip_address(address)
        except ValueError:
            print(f"Invalid IPv4 address correctly rejected: {address}")


# ---------------------------------------------------------------------------
# 5. IPV6 ADDRESSING
# ---------------------------------------------------------------------------

def demonstrate_ipv6() -> None:
    print("\nIPv6 ADDRESSING")
    print("-" * 72)

    addresses = [
        "::1",
        "2001:db8::1",
        "fe80::1234",
    ]

    for address in addresses:
        ip = ipaddress.ip_address(address)
        print(
            f"{ip} | version={ip.version} | "
            f"compressed={ip.compressed} | "
            f"exploded={ip.exploded}"
        )


# ---------------------------------------------------------------------------
# 6. SUBNETTING
# ---------------------------------------------------------------------------

def subnet_report(network_text: str) -> None:
    """Print useful properties of an IPv4 subnet."""

    network = ipaddress.ip_network(network_text, strict=False)

    print(f"\nNetwork: {network}")
    print(f"Address: {network.network_address}")
    print(f"Netmask: {network.netmask}")
    print(f"Prefix: /{network.prefixlen}")
    print(f"Broadcast: {network.broadcast_address}")
    print(f"Total addresses: {network.num_addresses}")

    if network.num_addresses > 2:
        hosts = list(network.hosts())
        print(f"First host: {hosts[0]}")
        print(f"Last host: {hosts[-1]}")
        print(f"Usable hosts: {len(hosts)}")
    else:
        print("Traditional host range is not available for this tiny subnet.")


def demonstrate_subnetting() -> None:
    print("\nSUBNETTING")
    print("-" * 72)

    for network in [
        "192.168.1.0/24",
        "192.168.1.0/26",
        "10.0.0.0/30",
        "2001:db8::/64",
    ]:
        network_object = ipaddress.ip_network(network, strict=False)
        print(f"{network} -> {network_object}")

        if network_object.version == 4:
            subnet_report(network)


# ---------------------------------------------------------------------------
# 7. ROUTING AND LONGEST PREFIX MATCH
# ---------------------------------------------------------------------------

@dataclass
class Route:
    """A simplified routing table entry."""

    network: ipaddress._BaseNetwork
    next_hop: str
    interface: str


class RoutingTable:
    """A small educational routing-table implementation."""

    def __init__(self) -> None:
        self.routes: List[Route] = []

    def add_route(
        self,
        network: str,
        next_hop: str,
        interface: str,
    ) -> None:
        self.routes.append(
            Route(
                ipaddress.ip_network(network, strict=False),
                next_hop,
                interface,
            )
        )

    def lookup(self, destination: str) -> Optional[Route]:
        """
        Select the matching route with the longest prefix.

        Longest-prefix matching allows a more specific route to override
        a broad route such as 0.0.0.0/0.
        """

        address = ipaddress.ip_address(destination)
        matches = [
            route
            for route in self.routes
            if address in route.network
        ]

        if not matches:
            return None

        return max(matches, key=lambda route: route.network.prefixlen)


def demonstrate_routing() -> None:
    print("\nROUTING")
    print("-" * 72)

    table = RoutingTable()
    table.add_route("0.0.0.0/0", "192.168.1.1", "eth0")
    table.add_route("10.0.0.0/8", "192.168.1.254", "eth1")
    table.add_route("10.10.0.0/16", "192.168.1.253", "eth2")
    table.add_route("10.10.20.0/24", "192.168.1.252", "eth3")

    for destination in [
        "8.8.8.8",
        "10.20.1.5",
        "10.10.5.10",
        "10.10.20.42",
    ]:
        route = table.lookup(destination)

        if route is None:
            print(f"{destination}: no route")
        else:
            print(
                f"{destination}: {route.network} -> "
                f"next hop {route.next_hop}, interface {route.interface}"
            )


# ---------------------------------------------------------------------------
# 8. IPV4 HEADER CHECKSUM
# ---------------------------------------------------------------------------

def internet_checksum(data: bytes) -> int:
    """
    Calculate the standard Internet checksum.

    The algorithm:
    1. Treat data as 16-bit words.
    2. Add them using one's-complement arithmetic.
    3. Fold carries back into the lower 16 bits.
    4. Complement the final value.
    """

    if len(data) % 2:
        data += b"\x00"

    total = 0

    for index in range(0, len(data), 2):
        word = (data[index] << 8) | data[index + 1]
        total += word
        total = (total & 0xFFFF) + (total >> 16)

    total = (total & 0xFFFF) + (total >> 16)

    return (~total) & 0xFFFF


def demonstrate_checksum() -> None:
    print("\nINTERNET CHECKSUM")
    print("-" * 72)

    message = b"TCP/IP educational checksum example"
    checksum = internet_checksum(message)

    print(f"Data: {message!r}")
    print(f"Checksum: 0x{checksum:04x}")


# ---------------------------------------------------------------------------
# 9. UDP
# ---------------------------------------------------------------------------

@dataclass
class UDPDatagram:
    source_port: int
    destination_port: int
    payload: bytes

    def encode(self) -> bytes:
        """Encode a minimal UDP header plus payload."""

        length = 8 + len(self.payload)
        checksum = 0

        return struct.pack(
            "!HHHH",
            self.source_port,
            self.destination_port,
            length,
            checksum,
        ) + self.payload

    @classmethod
    def decode(cls, data: bytes) -> "UDPDatagram":
        if len(data) < 8:
            raise ValueError("UDP datagram is shorter than its 8-byte header")

        source, destination, length, checksum = struct.unpack(
            "!HHHH",
            data[:8],
        )

        if length < 8 or length > len(data):
            raise ValueError("Invalid UDP length field")

        return cls(
            source,
            destination,
            data[8:length],
        )


def demonstrate_udp() -> None:
    print("\nUDP")
    print("-" * 72)

    datagram = UDPDatagram(
        source_port=50000,
        destination_port=53,
        payload=b"DNS query payload",
    )

    encoded = datagram.encode()
    decoded = UDPDatagram.decode(encoded)

    print(f"Encoded bytes: {encoded.hex()}")
    print(
        f"Decoded ports: {decoded.source_port} -> "
        f"{decoded.destination_port}"
    )
    print(f"Payload: {decoded.payload!r}")

    print(
        "UDP is connectionless and does not provide TCP-style "
        "retransmission, ordering, or congestion control."
    )


# ---------------------------------------------------------------------------
# 10. TCP STATE MACHINE
# ---------------------------------------------------------------------------

class TCPState(Enum):
    CLOSED = "CLOSED"
    LISTEN = "LISTEN"
    SYN_SENT = "SYN-SENT"
    SYN_RECEIVED = "SYN-RECEIVED"
    ESTABLISHED = "ESTABLISHED"
    FIN_WAIT_1 = "FIN-WAIT-1"
    FIN_WAIT_2 = "FIN-WAIT-2"
    CLOSE_WAIT = "CLOSE-WAIT"
    LAST_ACK = "LAST-ACK"
    TIME_WAIT = "TIME-WAIT"


@dataclass
class TCPEndpoint:
    name: str
    state: TCPState = TCPState.CLOSED
    sequence_number: int = 0
    acknowledgment_number: int = 0

    def listen(self) -> None:
        self.state = TCPState.LISTEN

    def send_syn(self) -> None:
        if self.state != TCPState.CLOSED:
            raise RuntimeError("SYN can only start from CLOSED in this model")

        self.sequence_number = random.randint(1_000, 9_999)
        self.state = TCPState.SYN_SENT

    def receive_syn(self, peer_sequence: int) -> None:
        if self.state != TCPState.LISTEN:
            raise RuntimeError("Endpoint must be listening")

        self.acknowledgment_number = peer_sequence + 1
        self.sequence_number = random.randint(1_000, 9_999)
        self.state = TCPState.SYN_RECEIVED

    def receive_syn_ack(self, peer_sequence: int) -> None:
        if self.state != TCPState.SYN_SENT:
            raise RuntimeError("Unexpected SYN-ACK")

        self.acknowledgment_number = peer_sequence + 1
        self.state = TCPState.ESTABLISHED

    def receive_final_ack(self) -> None:
        if self.state != TCPState.SYN_RECEIVED:
            raise RuntimeError("Unexpected final ACK")

        self.state = TCPState.ESTABLISHED


def demonstrate_tcp_handshake() -> None:
    print("\nTCP THREE-WAY HANDSHAKE")
    print("-" * 72)

    client = TCPEndpoint("client")
    server = TCPEndpoint("server")

    server.listen()
    client.send_syn()

    print(f"1. Client sends SYN: {client.state.value}")
    server.receive_syn(client.sequence_number)

    print(f"2. Server sends SYN-ACK: {server.state.value}")
    client.receive_syn_ack(server.sequence_number)

    print(f"3. Client sends ACK: {client.state.value}")
    server.receive_final_ack()

    print(f"Client: {client.state.value}")
    print(f"Server: {server.state.value}")


# ---------------------------------------------------------------------------
# 11. TCP RELIABILITY SIMULATION
# ---------------------------------------------------------------------------

@dataclass
class ReliablePacket:
    sequence_number: int
    payload: bytes
    acknowledged: bool = False
    attempts: int = 0


class ReliableChannel:
    """
    A deliberately simple reliability simulation.

    Real TCP uses a much richer mechanism involving sequence numbers,
    acknowledgments, retransmission timers, congestion control,
    receive windows, selective acknowledgment and other behaviors.
    """

    def __init__(self, loss_probability: float = 0.2) -> None:
        if not 0 <= loss_probability <= 1:
            raise ValueError("Loss probability must be between 0 and 1")

        self.loss_probability = loss_probability

    def transmit(self, packet: ReliablePacket) -> bool:
        packet.attempts += 1

        if random.random() < self.loss_probability:
            return False

        packet.acknowledged = True
        return True


def demonstrate_reliability() -> None:
    print("\nRELIABLE DELIVERY SIMULATION")
    print("-" * 72)

    random.seed(42)

    channel = ReliableChannel(loss_probability=0.35)
    packets = [
        ReliablePacket(index, f"payload-{index}".encode())
        for index in range(1, 6)
    ]

    maximum_attempts = 10

    for packet in packets:
        while not packet.acknowledged:
            delivered = channel.transmit(packet)

            if delivered:
                print(
                    f"Sequence {packet.sequence_number}: "
                    f"ACK received after {packet.attempts} attempt(s)"
                )
            elif packet.attempts >= maximum_attempts:
                print(
                    f"Sequence {packet.sequence_number}: "
                    f"failed after {packet.attempts} attempts"
                )
                break
            else:
                print(
                    f"Sequence {packet.sequence_number}: "
                    f"loss detected, retransmitting"
                )


# ---------------------------------------------------------------------------
# 12. PORTS
# ---------------------------------------------------------------------------

COMMON_PORTS = {
    20: "FTP data",
    21: "FTP control",
    22: "SSH",
    25: "SMTP",
    53: "DNS",
    67: "DHCP server",
    68: "DHCP client",
    80: "HTTP",
    110: "POP3",
    123: "NTP",
    143: "IMAP",
    443: "HTTPS",
    3306: "MySQL",
    5432: "PostgreSQL",
    6379: "Redis",
    8080: "Common alternate HTTP application port",
}


def demonstrate_ports() -> None:
    print("\nPORTS")
    print("-" * 72)

    for port in [22, 53, 80, 443, 5432, 9999]:
        print(
            f"Port {port}: "
            f"{COMMON_PORTS.get(port, 'No common service mapping in this table')}"
        )

    print(
        "\nA port identifies a transport-layer endpoint for a process. "
        "An IP address identifies a network interface or host-level endpoint."
    )


# ---------------------------------------------------------------------------
# 13. DNS CONCEPTUAL SIMULATION
# ---------------------------------------------------------------------------

@dataclass
class DNSRecord:
    name: str
    record_type: str
    value: str
    ttl: int = 300


class DNSCache:
    """A simple DNS cache with expiration."""

    def __init__(self) -> None:
        self.records: Dict[Tuple[str, str], Tuple[DNSRecord, float]] = {}

    def put(self, record: DNSRecord) -> None:
        expiration = time.time() + record.ttl
        self.records[(record.name.lower(), record.record_type)] = (
            record,
            expiration,
        )

    def get(
        self,
        name: str,
        record_type: str,
    ) -> Optional[DNSRecord]:
        key = (name.lower(), record_type)
        entry = self.records.get(key)

        if entry is None:
            return None

        record, expiration = entry

        if time.time() >= expiration:
            del self.records[key]
            return None

        return record


def demonstrate_dns() -> None:
    print("\nDNS")
    print("-" * 72)

    cache = DNSCache()

    cache.put(
        DNSRecord(
            name="example.com",
            record_type="A",
            value="93.184.216.34",
            ttl=60,
        )
    )

    cached = cache.get("EXAMPLE.COM", "A")

    if cached:
        print(
            f"Cached DNS answer: {cached.name} "
            f"{cached.record_type} {cached.value}"
        )

    print(
        "DNS translates names into records such as A, AAAA, MX, "
        "CNAME, NS and TXT records."
    )


# ---------------------------------------------------------------------------
# 14. HTTP REQUEST SIMULATION
# ---------------------------------------------------------------------------

@dataclass
class HTTPRequest:
    method: str
    target: str
    headers: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    def serialize(self) -> bytes:
        lines = [
            f"{self.method} {self.target} HTTP/1.1",
            *[
                f"{name}: {value}"
                for name, value in self.headers.items()
            ],
            "",
            self.body.decode("utf-8", errors="replace"),
        ]

        return "\r\n".join(lines).encode()


def demonstrate_http() -> None:
    print("\nHTTP")
    print("-" * 72)

    request = HTTPRequest(
        method="GET",
        target="/products",
        headers={
            "Host": "example.com",
            "Accept": "application/json",
            "Connection": "close",
        },
    )

    print(request.serialize().decode())


# ---------------------------------------------------------------------------
# 15. DHCP CONCEPTUAL FLOW
# ---------------------------------------------------------------------------

def demonstrate_dhcp() -> None:
    print("\nDHCP")
    print("-" * 72)

    flow = [
        "DHCPDISCOVER: client searches for a DHCP server",
        "DHCPOFFER: server proposes configuration",
        "DHCPREQUEST: client requests the offered configuration",
        "DHCPACK: server confirms the lease",
    ]

    for step in flow:
        print(step)

    print(
        "DHCP commonly provides an IP address, subnet mask, default gateway "
        "and DNS-server information."
    )


# ---------------------------------------------------------------------------
# 16. ICMP
# ---------------------------------------------------------------------------

@dataclass
class ICMPMessage:
    message_type: int
    code: int
    payload: bytes

    def checksum(self) -> int:
        header = struct.pack("!BBH", self.message_type, self.code, 0)
        return internet_checksum(header + self.payload)


def demonstrate_icmp() -> None:
    print("\nICMP")
    print("-" * 72)

    echo_request = ICMPMessage(
        message_type=8,
        code=0,
        payload=b"ping",
    )

    print("ICMP Echo Request")
    print(f"Type: {echo_request.message_type}")
    print(f"Code: {echo_request.code}")
    print(f"Checksum: 0x{echo_request.checksum():04x}")
    print(
        "Ping uses ICMP Echo Request and Echo Reply messages. "
        "ICMP is carried directly by IP rather than by TCP or UDP."
    )


# ---------------------------------------------------------------------------
# 17. NAT
# ---------------------------------------------------------------------------

@dataclass
class NATMapping:
    private_ip: str
    private_port: int
    public_ip: str
    public_port: int
    destination_ip: str
    destination_port: int


class NATTable:
    """A simplified stateful NAT mapping table."""

    def __init__(self, public_ip: str) -> None:
        self.public_ip = public_ip
        self.next_port = 40000
        self.mappings: Dict[Tuple[str, int, str, int], NATMapping] = {}

    def translate(
        self,
        private_ip: str,
        private_port: int,
        destination_ip: str,
        destination_port: int,
    ) -> NATMapping:
        key = (
            private_ip,
            private_port,
            destination_ip,
            destination_port,
        )

        if key in self.mappings:
            return self.mappings[key]

        mapping = NATMapping(
            private_ip=private_ip,
            private_port=private_port,
            public_ip=self.public_ip,
            public_port=self.next_port,
            destination_ip=destination_ip,
            destination_port=destination_port,
        )

        self.next_port += 1
        self.mappings[key] = mapping
        return mapping


def demonstrate_nat() -> None:
    print("\nNAT")
    print("-" * 72)

    nat = NATTable("203.0.113.10")

    mapping = nat.translate(
        "192.168.1.20",
        51000,
        "93.184.216.34",
        443,
    )

    print(
        f"{mapping.private_ip}:{mapping.private_port} -> "
        f"{mapping.public_ip}:{mapping.public_port}"
    )

    print(
        "NAT allows many private hosts to share public IPv4 addresses. "
        "It changes addressing information and often tracks transport ports."
    )


# ---------------------------------------------------------------------------
# 18. MTU AND FRAGMENTATION
# ---------------------------------------------------------------------------

def fragment_payload(
    payload: bytes,
    mtu: int,
    ip_header_size: int = 20,
) -> List[bytes]:
    """
    Educational IPv4 payload fragmentation model.

    IPv4 fragments normally use fragment offsets measured in units of
    eight bytes. The implementation here returns payload chunks and
    demonstrates the alignment constraint.
    """

    if mtu <= ip_header_size:
        raise ValueError("MTU must be larger than the IP header")

    maximum_payload = mtu - ip_header_size
    aligned_payload = (maximum_payload // 8) * 8

    if aligned_payload <= 0:
        raise ValueError("MTU leaves no valid fragment payload")

    fragments = [
        payload[index:index + aligned_payload]
        for index in range(0, len(payload), aligned_payload)
    ]

    return fragments


def demonstrate_mtu() -> None:
    print("\nMTU AND FRAGMENTATION")
    print("-" * 72)

    payload = bytes(range(100))

    fragments = fragment_payload(
        payload,
        mtu=44,
        ip_header_size=20,
    )

    print(f"Original payload: {len(payload)} bytes")
    print(
        "Fragment sizes:",
        [len(fragment) for fragment in fragments],
    )

    print(
        "Modern networks often avoid fragmentation where possible through "
        "path-MTU discovery and appropriate packet sizing."
    )


# ---------------------------------------------------------------------------
# 19. SOCKET ADDRESSING
# ---------------------------------------------------------------------------

def demonstrate_socket_addressing() -> None:
    print("\nSOCKET ADDRESSING")
    print("-" * 72)

    examples = [
        ("127.0.0.1", 8080),
        ("192.168.1.10", 443),
        ("0.0.0.0", 5000),
    ]

    for host, port in examples:
        print(f"Socket endpoint: {host}:{port}")

    print(
        "A TCP socket is commonly identified by local and remote IP/port "
        "information plus the transport protocol."
    )


# ---------------------------------------------------------------------------
# 20. REAL SOCKET EXAMPLE
# ---------------------------------------------------------------------------

def demonstrate_local_socket() -> None:
    """
    Use a loopback TCP connection.

    This is a real operating-system networking operation rather than
    a pure simulation. The socket is bound to localhost only.
    """

    print("\nREAL LOOPBACK TCP SOCKET")
    print("-" * 72)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind(("127.0.0.1", 0))
        server.listen(1)

        address, port = server.getsockname()

        print(f"Server listening on {address}:{port}")

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            client.connect((address, port))

            connection, client_address = server.accept()

            try:
                client.sendall(b"hello TCP/IP")
                received = connection.recv(1024)

                if received:
                    connection.sendall(received.upper())

                response = client.recv(1024)
                print(f"Client received: {response!r}")
                print(f"Peer address: {client_address}")
            finally:
                connection.close()
        finally:
            client.close()

    finally:
        server.close()


# ---------------------------------------------------------------------------
# 21. TCP VS UDP COMPARISON
# ---------------------------------------------------------------------------

def compare_tcp_udp() -> None:
    print("\nTCP VS UDP")
    print("-" * 72)

    comparison = [
        ("Connection model", "Connection-oriented", "Connectionless"),
        ("Ordering", "Provides ordered byte stream", "No inherent ordering"),
        ("Retransmission", "Yes", "No built-in retransmission"),
        ("Flow control", "Yes", "No TCP-style flow control"),
        ("Congestion control", "Yes", "Not inherently"),
        ("Typical overhead", "Higher", "Lower"),
        ("Common uses", "HTTP/HTTPS, SSH", "DNS, streaming, games, QUIC"),
    ]

    print(
        f"{'Property':<22} {'TCP':<30} {'UDP':<30}"
    )

    for property_name, tcp, udp in comparison:
        print(
            f"{property_name:<22} "
            f"{tcp:<30} "
            f"{udp:<30}"
        )


# ---------------------------------------------------------------------------
# 22. OSI AND TCP/IP COMPARISON
# ---------------------------------------------------------------------------

def compare_models() -> None:
    print("\nOSI MODEL VS TCP/IP MODEL")
    print("-" * 72)

    mapping = [
        ("OSI Application", "TCP/IP Application"),
        ("OSI Presentation", "TCP/IP Application"),
        ("OSI Session", "TCP/IP Application"),
        ("OSI Transport", "TCP/IP Transport"),
        ("OSI Network", "TCP/IP Internet"),
        ("OSI Data Link", "TCP/IP Network Access"),
        ("OSI Physical", "TCP/IP Network Access"),
    ]

    for osi, tcpip in mapping:
        print(f"{osi:<25} -> {tcpip}")


# ---------------------------------------------------------------------------
# 23. PROTOCOL STACK TRACE
# ---------------------------------------------------------------------------

def protocol_stack_for_https() -> List[str]:
    """
    Return a simplified HTTPS stack.

    HTTPS is HTTP protected by TLS. TLS is usually treated as an
    application-layer security protocol in the four-layer TCP/IP model,
    although architectural diagrams sometimes place it between
    application and transport.
    """

    return [
        "HTTPS / HTTP",
        "TLS",
        "TCP",
        "IPv4 or IPv6",
        "Ethernet or Wi-Fi",
    ]


def demonstrate_protocol_stack() -> None:
    print("\nHTTPS PROTOCOL STACK")
    print("-" * 72)

    for position, protocol in enumerate(
        protocol_stack_for_https(),
        start=1,
    ):
        print(f"{position}. {protocol}")


# ---------------------------------------------------------------------------
# 24. SECURITY CONSIDERATIONS
# ---------------------------------------------------------------------------

def demonstrate_security() -> None:
    print("\nSECURITY CONSIDERATIONS")
    print("-" * 72)

    security_points = [
        (
            "Ethernet/Wi-Fi",
            "Use link-layer protections such as WPA2/WPA3 where applicable."
        ),
        (
            "IP",
            "Use filtering, routing controls and appropriate segmentation."
        ),
        (
            "TCP/UDP",
            "Restrict exposed ports and validate traffic."
        ),
        (
            "Application",
            "Use TLS, authentication, authorization and input validation."
        ),
        (
            "DNS",
            "Consider DNSSEC, encrypted DNS and protection against spoofing."
        ),
    ]

    for layer, recommendation in security_points:
        print(f"{layer}: {recommendation}")


# ---------------------------------------------------------------------------
# 25. PERFORMANCE CONSIDERATIONS
# ---------------------------------------------------------------------------

def demonstrate_performance() -> None:
    print("\nPERFORMANCE CONSIDERATIONS")
    print("-" * 72)

    factors = {
        "Bandwidth": "How much data can be transferred per unit of time.",
        "Latency": "Time required for data to travel between endpoints.",
        "Jitter": "Variation in packet delay.",
        "Packet loss": "Packets that fail to reach the destination.",
        "MTU": "Maximum packet/frame payload size allowed on a link.",
        "RTT": "Round-trip time between endpoints.",
        "Window size": "Amount of outstanding data allowed before acknowledgment.",
    }

    for factor, explanation in factors.items():
        print(f"{factor:<18}: {explanation}")


# ---------------------------------------------------------------------------
# 26. TROUBLESHOOTING ORDER
# ---------------------------------------------------------------------------

def troubleshooting_checklist() -> None:
    print("\nTCP/IP TROUBLESHOOTING CHECKLIST")
    print("-" * 72)

    checks = [
        "1. Check physical/link connectivity.",
        "2. Check interface state and local MAC configuration.",
        "3. Check IP address and subnet configuration.",
        "4. Check default gateway and routing table.",
        "5. Test local gateway reachability.",
        "6. Test remote IP reachability.",
        "7. Test DNS resolution separately from IP connectivity.",
        "8. Check whether the destination TCP/UDP port is reachable.",
        "9. Check application-layer protocol behavior.",
        "10. Inspect packet captures when the fault is not obvious.",
    ]

    for check in checks:
        print(check)


# ---------------------------------------------------------------------------
# 27. PACKET-CAPTURE INTERPRETATION
# ---------------------------------------------------------------------------

def demonstrate_packet_capture_reasoning() -> None:
    print("\nPACKET CAPTURE REASONING")
    print("-" * 72)

    observations = [
        (
            "Ethernet frame arrives",
            "Network access layer is carrying the frame."
        ),
        (
            "Destination IP is visible",
            "Internet-layer addressing can be inspected."
        ),
        (
            "TCP destination port is 443",
            "The transport endpoint is associated with HTTPS traffic."
        ),
        (
            "TLS records follow",
            "The application payload is protected by TLS."
        ),
        (
            "TCP retransmissions appear",
            "Packet loss, congestion or another transport-path issue may exist."
        ),
    ]

    for observation, interpretation in observations:
        print(f"{observation}: {interpretation}")


# ---------------------------------------------------------------------------
# 28. EDGE CASES
# ---------------------------------------------------------------------------

def demonstrate_edge_cases() -> None:
    print("\nEDGE CASES")
    print("-" * 72)

    cases = [
        "TCP connection to a closed port may receive a reset.",
        "UDP traffic may receive no response at all.",
        "DNS can return multiple addresses.",
        "A host can have multiple network interfaces.",
        "IPv4 and IPv6 can operate simultaneously.",
        "A route can exist but a firewall can still block the traffic.",
        "Ping can fail even when an application works because ICMP may be filtered.",
        "DNS failure does not necessarily mean IP connectivity has failed.",
        "A successful TCP connection does not prove the application protocol is healthy.",
        "NAT can make private and public addresses differ during communication.",
    ]

    for case in cases:
        print(f"- {case}")


# ---------------------------------------------------------------------------
# 29. HASHING FOR DATA INTEGRITY CONTEXT
# ---------------------------------------------------------------------------

def demonstrate_application_integrity() -> None:
    print("\nAPPLICATION-LEVEL INTEGRITY EXAMPLE")
    print("-" * 72)

    payload = b"network message"

    digest = hashlib.sha256(payload).hexdigest()

    print(f"Payload: {payload!r}")
    print(f"SHA-256: {digest}")

    print(
        "Cryptographic hashes can detect changes to data, but a bare hash "
        "does not authenticate who created the data. Authentication requires "
        "additional mechanisms such as MACs, signatures or authenticated TLS."
    )


# ---------------------------------------------------------------------------
# 30. COMPLETE LEARNING DEMONSTRATION
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 72)
    print("TCP/IP MODEL: COMPREHENSIVE PYTHON STUDY PROGRAM")
    print("=" * 72)

    print_model()
    demonstrate_encapsulation()
    demonstrate_mac_addresses()
    demonstrate_ipv4()
    demonstrate_ipv6()
    demonstrate_subnetting()
    demonstrate_routing()
    demonstrate_checksum()
    demonstrate_udp()
    demonstrate_tcp_handshake()
    demonstrate_reliability()
    demonstrate_ports()
    demonstrate_dns()
    demonstrate_http()
    demonstrate_dhcp()
    demonstrate_icmp()
    demonstrate_nat()
    demonstrate_mtu()
    demonstrate_socket_addressing()

    try:
        demonstrate_local_socket()
    except OSError as exc:
        # Real socket operations can fail because of local operating-system
        # restrictions. The conceptual demonstrations remain usable.
        print(f"Loopback socket demonstration could not run: {exc}")

    compare_tcp_udp()
    compare_models()
    demonstrate_protocol_stack()
    demonstrate_security()
    demonstrate_performance()
    troubleshooting_checklist()
    demonstrate_packet_capture_reasoning()
    demonstrate_edge_cases()
    demonstrate_application_integrity()

    print("\nSTUDY COMPLETE")
    print(
        "The central idea is that the TCP/IP model separates networking "
        "responsibilities into layers while protocols at those layers "
        "cooperate to deliver application data across interconnected networks."
    )


if __name__ == "__main__":
    main()
