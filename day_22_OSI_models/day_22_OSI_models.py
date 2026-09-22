"""
OSI Model: From Fundamentals to Advanced Networking Concepts

A self-contained study program covering the seven-layer OSI reference model,
its terminology, encapsulation, addressing, protocols, devices, troubleshooting,
security, performance, and practical packet-flow simulations.

The program uses only Python's standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Tuple
import ipaddress
import struct
import time


class OSILayer(IntEnum):
    """The seven OSI layers, numbered from bottom to top."""

    PHYSICAL = 1
    DATA_LINK = 2
    NETWORK = 3
    TRANSPORT = 4
    SESSION = 5
    PRESENTATION = 6
    APPLICATION = 7


LAYER_NAMES = {
    OSILayer.PHYSICAL: "Physical",
    OSILayer.DATA_LINK: "Data Link",
    OSILayer.NETWORK: "Network",
    OSILayer.TRANSPORT: "Transport",
    OSILayer.SESSION: "Session",
    OSILayer.PRESENTATION: "Presentation",
    OSILayer.APPLICATION: "Application",
}

PDU_NAMES = {
    OSILayer.PHYSICAL: "Bits",
    OSILayer.DATA_LINK: "Frame",
    OSILayer.NETWORK: "Packet",
    OSILayer.TRANSPORT: "Segment / Datagram",
    OSILayer.SESSION: "Data",
    OSILayer.PRESENTATION: "Data",
    OSILayer.APPLICATION: "Data",
}


def print_title(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def print_layer_table() -> None:
    """Display the seven layers, their PDUs, examples, and common devices."""

    rows = [
        (1, "Physical", "Bits", "Ethernet PHY, fiber, radio", "Hub, repeater"),
        (2, "Data Link", "Frame", "Ethernet, Wi-Fi, ARP", "Switch, bridge"),
        (3, "Network", "Packet", "IPv4, IPv6, ICMP", "Router"),
        (4, "Transport", "Segment/Datagram", "TCP, UDP", "L4 firewall/load balancer"),
        (5, "Session", "Data", "Sessions, RPC, dialogs", "Session-aware gateway"),
        (6, "Presentation", "Data", "TLS, encoding, compression", "TLS proxy/gateway"),
        (7, "Application", "Data", "HTTP, DNS, SMTP, SSH", "Proxy, application gateway"),
    ]

    print(f"{'No.':<5}{'Layer':<15}{'PDU':<20}{'Examples':<30}{'Devices':<25}")
    print("-" * 95)
    for number, name, pdu, protocols, devices in rows:
        print(f"{number:<5}{name:<15}{pdu:<20}{protocols:<30}{devices:<25}")


def demonstrate_layer_roles() -> None:
    """Explain the responsibility of each layer through executable data."""

    print_title("1. OSI Layer Responsibilities")
    print_layer_table()

    responsibilities = {
        1: "Moves raw electrical, optical, or radio signals.",
        2: "Provides local-link framing and hardware addressing.",
        3: "Provides logical addressing and routing between networks.",
        4: "Provides end-to-end transport, ports, reliability, and flow control.",
        5: "Manages logical communication sessions and dialog state.",
        6: "Handles representation, encoding, compression, and encryption.",
        7: "Provides network services directly to applications.",
    }

    print("\nResponsibilities:")
    for layer in range(1, 8):
        print(f"L{layer} {LAYER_NAMES[OSILayer(layer)]}: {responsibilities[layer]}")


def demonstrate_encapsulation() -> None:
    """
    Model encapsulation and decapsulation.

    Real network stacks do not literally create these Python objects, but this
    representation makes the relationship between headers, payloads, and PDUs
    explicit.
    """

    print_title("2. Encapsulation and Decapsulation")

    application_data = "GET /index.html HTTP/1.1"
    presentation_data = f"TLS/encoded({application_data})"
    session_data = f"SESSION[{presentation_data}]"
    tcp_header = "TCP src=51500 dst=443 seq=1001 ack=5001"
    ip_header = "IPv4 src=192.168.1.20 dst=203.0.113.10"
    ethernet_header = "Ethernet src=AA:BB:CC:DD:EE:01 dst=AA:BB:CC:DD:EE:FE"
    physical_bits = "01001000 01010100 01010100 ..."

    units = [
        ("Application Data", application_data),
        ("Presentation Data", presentation_data),
        ("Session Data", session_data),
        ("Transport Segment", f"[{tcp_header}] {session_data}"),
        ("Network Packet", f"[{ip_header}] [{tcp_header}] {session_data}"),
        (
            "Data-Link Frame",
            f"[{ethernet_header}] [{ip_header}] [{tcp_header}] {session_data}",
        ),
        ("Physical Bits", physical_bits),
    ]

    for name, content in units:
        print(f"{name:<22}: {content}")

    print("\nDecapsulation reverses the process:")
    for name, _ in reversed(units):
        print(f"Received -> process {name}")


def demonstrate_addressing() -> None:
    """Show the distinction among MAC addresses, IP addresses, and ports."""

    print_title("3. Addressing at Different Layers")

    mac_address = "AA:BB:CC:DD:EE:01"
    ip_address = ipaddress.ip_address("192.168.10.25")
    network = ipaddress.ip_network("192.168.10.0/24")
    port = 443

    print(f"Layer 2 MAC address : {mac_address}")
    print(f"Layer 3 IP address  : {ip_address}")
    print(f"Network             : {network}")
    print(f"Layer 4 port        : {port}")

    print("\nAddressing relationship:")
    print("MAC identifies a network interface on a local data-link network.")
    print("IP identifies a logical endpoint used for inter-network routing.")
    print("A transport port identifies a service/application endpoint.")


def demonstrate_ipv4_header() -> None:
    """Build and inspect a simplified IPv4 header."""

    print_title("4. Network Layer: IPv4 Header")

    version = 4
    ihl = 5
    ttl = 64
    protocol = 6  # TCP
    source = ipaddress.ip_address("192.168.1.20")
    destination = ipaddress.ip_address("203.0.113.10")

    first_byte = (version << 4) | ihl
    header = struct.pack(
        "!BBHBBH4s4s",
        first_byte,
        0,
        40,
        0,
        ttl,
        protocol,
        source.packed,
        destination.packed,
    )

    print(f"Version       : {version}")
    print(f"IHL           : {ihl} words")
    print(f"TTL           : {ttl}")
    print(f"Protocol      : {protocol} (TCP)")
    print(f"Source IP     : {source}")
    print(f"Destination IP: {destination}")
    print(f"Simplified header bytes: {header.hex()}")


@dataclass
class EthernetFrame:
    """Simplified Ethernet frame used for teaching."""

    source_mac: str
    destination_mac: str
    ether_type: int
    payload: str

    def describe(self) -> None:
        print(f"Ethernet source      : {self.source_mac}")
        print(f"Ethernet destination : {self.destination_mac}")
        print(f"EtherType            : 0x{self.ether_type:04X}")
        print(f"Payload              : {self.payload}")


@dataclass
class IPPacket:
    """Simplified IP packet."""

    source_ip: str
    destination_ip: str
    protocol: str
    payload: str
    ttl: int = 64

    def forward(self) -> bool:
        """
        A router decrements TTL.

        A packet whose TTL reaches zero is discarded and normally results in
        an ICMP Time Exceeded message.
        """
        self.ttl -= 1
        return self.ttl > 0


@dataclass
class TCPSegment:
    """Simplified TCP segment."""

    source_port: int
    destination_port: int
    sequence_number: int
    acknowledgement_number: int
    flags: List[str]
    payload: str = ""

    def describe(self) -> None:
        print(f"TCP ports : {self.source_port} -> {self.destination_port}")
        print(f"Sequence  : {self.sequence_number}")
        print(f"Ack       : {self.acknowledgement_number}")
        print(f"Flags     : {', '.join(self.flags)}")
        print(f"Payload   : {self.payload!r}")


def demonstrate_tcp_handshake() -> None:
    """Simulate the TCP three-way handshake."""

    print_title("5. Transport Layer: TCP Three-Way Handshake")

    client_port = 51500
    server_port = 443
    client_isn = 10000
    server_isn = 70000

    messages = [
        TCPSegment(client_port, server_port, client_isn, 0, ["SYN"]),
        TCPSegment(server_port, client_port, server_isn, client_isn + 1, ["SYN", "ACK"]),
        TCPSegment(client_port, server_port, client_isn + 1, server_isn + 1, ["ACK"]),
    ]

    for index, message in enumerate(messages, start=1):
        print(f"\nHandshake message {index}")
        message.describe()


def demonstrate_udp_vs_tcp() -> None:
    """Compare transport protocols without declaring one universally superior."""

    print_title("6. TCP vs UDP")

    comparison = [
        ("Connection model", "Connection-oriented", "Connectionless"),
        ("Reliability", "Sequencing, acknowledgements, retransmission", "No built-in delivery guarantee"),
        ("Ordering", "Provides ordered byte stream", "No ordering guarantee"),
        ("Overhead", "Higher", "Lower"),
        ("Typical uses", "HTTPS, SSH, database connections", "DNS, streaming, real-time traffic"),
        ("Flow/congestion control", "Built in", "Application/protocol dependent"),
    ]

    print(f"{'Property':<25}{'TCP':<42}{'UDP':<42}")
    print("-" * 109)
    for property_name, tcp, udp in comparison:
        print(f"{property_name:<25}{tcp:<42}{udp:<42}")


def demonstrate_ports() -> None:
    """Explain well-known, registered, and ephemeral port ranges."""

    print_title("7. Transport Ports")

    services = {
        20: "FTP data",
        21: "FTP control",
        22: "SSH",
        25: "SMTP",
        53: "DNS",
        80: "HTTP",
        443: "HTTPS",
        3306: "Common MySQL port",
        5432: "Common PostgreSQL port",
    }

    for port, service in services.items():
        print(f"{port:>5} -> {service}")

    print("\nA TCP/UDP endpoint is commonly represented as IP address + port.")
    print("For example: 192.168.1.20:51500 -> 203.0.113.10:443")


def demonstrate_arp_concept() -> None:
    """Model the relationship between Layer 2 and Layer 3 addressing."""

    print_title("8. ARP: Connecting Layer 3 and Layer 2 on IPv4 LANs")

    arp_table: Dict[str, str] = {
        "192.168.1.1": "AA:AA:AA:AA:AA:01",
        "192.168.1.20": "AA:AA:AA:AA:AA:20",
        "192.168.1.30": "AA:AA:AA:AA:AA:30",
    }

    target_ip = "192.168.1.1"

    print(f"ARP lookup for {target_ip}")
    if target_ip in arp_table:
        print(f"Resolved MAC: {arp_table[target_ip]}")
    else:
        print("No ARP cache entry; an ARP request would normally be sent.")

    print("\nImportant distinction:")
    print("ARP is associated with IPv4 local-network address resolution.")
    print("IPv6 uses Neighbor Discovery rather than ARP.")


def demonstrate_switching_and_routing() -> None:
    """Simulate basic forwarding decisions at Layers 2 and 3."""

    print_title("9. Switch vs Router")

    switch_mac_table = {
        "AA:AA:AA:AA:AA:10": "Port 1",
        "AA:AA:AA:AA:AA:20": "Port 2",
        "AA:AA:AA:AA:AA:30": "Port 3",
    }

    destination_mac = "AA:AA:AA:AA:AA:20"
    print(f"Switch lookup for {destination_mac}: "
          f"{switch_mac_table.get(destination_mac, 'Unknown destination; flooding may occur')}")

    routing_table = [
        ("192.168.1.0/24", "LAN interface"),
        ("10.0.0.0/8", "Private network interface"),
        ("0.0.0.0/0", "Default gateway / upstream"),
    ]

    destination = ipaddress.ip_address("8.8.8.8")
    print(f"\nRouter lookup for {destination}")
    for network_text, next_hop in routing_table:
        network = ipaddress.ip_network(network_text)
        if destination in network:
            print(f"Matched {network} -> {next_hop}")
            break


def demonstrate_dns() -> None:
    """Simulate the conceptual steps of a DNS lookup."""

    print_title("10. Application Layer: DNS")

    domain = "example.com"
    simulated_dns_cache = {
        "example.com": "93.184.216.34",
        "localhost": "127.0.0.1",
    }

    print(f"Application requests address for: {domain}")
    if domain in simulated_dns_cache:
        print(f"DNS answer from simulated cache: {simulated_dns_cache[domain]}")
    else:
        print("A recursive DNS resolver would normally query authoritative infrastructure.")

    print("\nTypical DNS path:")
    print("Application -> Resolver -> Root -> TLD -> Authoritative server -> Answer")


def demonstrate_http_request() -> None:
    """Show HTTP as an application-layer protocol carried by lower layers."""

    print_title("11. Application Layer: HTTP")

    request = (
        "GET /index.html HTTP/1.1\r\n"
        "Host: example.com\r\n"
        "Accept: text/html\r\n"
        "Connection: close\r\n"
        "\r\n"
    )

    print(request)

    print("Conceptual encapsulation:")
    print("HTTP message")
    print("  inside TLS when HTTPS is used")
    print("    inside TCP")
    print("      inside IP")
    print("        inside Ethernet/Wi-Fi")
    print("          transmitted as physical signals")


def demonstrate_tls() -> None:
    """Explain TLS in relation to the OSI model without claiming a single fixed layer."""

    print_title("12. TLS and the OSI Model")

    print("TLS provides confidentiality, integrity, authentication, and key establishment.")
    print("It is commonly discussed between the OSI Presentation and Session concepts,")
    print("although modern networking stacks do not map cleanly to OSI layers.")
    print("HTTPS is HTTP carried through TLS, usually over TCP.")
    print("Modern HTTP/3 instead uses QUIC over UDP, changing the protocol stack.")


def demonstrate_quic() -> None:
    """Show why the OSI model is a conceptual reference rather than a literal stack."""

    print_title("13. Modern Protocol Stacks and the OSI Model")

    print("Traditional HTTPS example:")
    print("HTTP -> TLS -> TCP -> IP -> Ethernet/Wi-Fi -> Physical medium")

    print("\nHTTP/3 example:")
    print("HTTP/3 -> QUIC -> UDP -> IP -> Ethernet/Wi-Fi -> Physical medium")

    print("\nQUIC integrates transport functions above UDP, including")
    print("reliability, streams, congestion control, and encrypted transport metadata.")


@dataclass
class NetworkEvent:
    timestamp: float
    layer: OSILayer
    action: str
    details: str


@dataclass
class PacketTracer:
    """A small diagnostic event recorder."""

    events: List[NetworkEvent] = field(default_factory=list)

    def record(self, layer: OSILayer, action: str, details: str) -> None:
        self.events.append(
            NetworkEvent(time.time(), layer, action, details)
        )

    def show(self) -> None:
        for event in self.events:
            print(
                f"{event.timestamp:.3f} "
                f"L{event.layer.value} {LAYER_NAMES[event.layer]:<14} "
                f"{event.action:<14} {event.details}"
            )


def simulate_packet_trace() -> None:
    """Trace a simplified HTTPS packet from an application to a remote host."""

    print_title("14. End-to-End Packet Trace")

    tracer = PacketTracer()

    tracer.record(OSILayer.APPLICATION, "CREATE", "HTTPS request for example.com")
    tracer.record(OSILayer.PRESENTATION, "PROTECT", "TLS encryption/authentication")
    tracer.record(OSILayer.SESSION, "TRACK", "Logical communication state")
    tracer.record(OSILayer.TRANSPORT, "SEGMENT", "TCP destination port 443")
    tracer.record(OSILayer.NETWORK, "ROUTE", "IPv4 packet toward remote network")
    tracer.record(OSILayer.DATA_LINK, "FRAME", "Ethernet destination is next hop")
    tracer.record(OSILayer.PHYSICAL, "TRANSMIT", "Bits/signals on physical medium")

    print("Outbound processing:")
    tracer.show()

    print("\nAt the destination, processing occurs in reverse order.")
    tracer.events.reverse()
    tracer.show()


def demonstrate_subnetting() -> None:
    """Demonstrate CIDR, network address, broadcast address, and host capacity."""

    print_title("15. Advanced Layer 3: Subnetting")

    networks = [
        ipaddress.ip_network("192.168.10.0/24"),
        ipaddress.ip_network("192.168.10.0/26"),
        ipaddress.ip_network("10.20.0.0/16"),
    ]

    for network in networks:
        print(f"\nNetwork: {network}")
        print(f"Network address : {network.network_address}")
        print(f"Broadcast       : {network.broadcast_address}")
        print(f"Prefix length   : /{network.prefixlen}")
        print(f"Total addresses : {network.num_addresses}")

        if network.version == 4 and network.num_addresses >= 4:
            print(f"Usable host addresses (traditional model): {network.num_addresses - 2}")


def demonstrate_ipv6() -> None:
    """Show basic IPv6 addressing."""

    print_title("16. IPv6")

    addresses = [
        ipaddress.ip_address("2001:db8::1"),
        ipaddress.ip_address("fe80::1234"),
        ipaddress.ip_address("::1"),
    ]

    for address in addresses:
        print(f"{address} -> version={address.version}, compressed={address.compressed}")

    print("\nIPv6 uses 128-bit addresses and does not use IPv4 ARP.")
    print("Neighbor Discovery operates through ICMPv6.")


def demonstrate_routing_algorithm() -> None:
    """
    Implement longest-prefix matching.

    Routers can have multiple matching routes. The route with the longest
    prefix is normally the most specific matching route.
    """

    print_title("17. Longest-Prefix Matching")

    routes = [
        ("0.0.0.0/0", "Internet gateway"),
        ("10.0.0.0/8", "Private router"),
        ("10.20.0.0/16", "Data-center router"),
        ("10.20.30.0/24", "Application subnet"),
    ]

    destination = ipaddress.ip_address("10.20.30.44")
    matching = [
        (ipaddress.ip_network(network), next_hop)
        for network, next_hop in routes
        if destination in ipaddress.ip_network(network)
    ]

    best_network, best_next_hop = max(matching, key=lambda item: item[0].prefixlen)

    print(f"Destination : {destination}")
    print("Matching routes:")
    for network, next_hop in matching:
        print(f"  {network:<18} -> {next_hop}")

    print(f"Selected route: {best_network} -> {best_next_hop}")


def demonstrate_mtu_fragmentation_concept() -> None:
    """Explain MTU and fragmentation without performing real network I/O."""

    print_title("18. MTU and Fragmentation")

    packet_size = 4000
    mtu = 1500
    ip_header_size = 20

    if packet_size <= mtu:
        print("Packet fits within the MTU.")
        return

    payload_per_fragment = mtu - ip_header_size
    fragment_count = (packet_size - ip_header_size + payload_per_fragment - 1) // payload_per_fragment

    print(f"Original packet size : {packet_size} bytes")
    print(f"Path MTU             : {mtu} bytes")
    print(f"Approx. IPv4 payload per fragment: {payload_per_fragment} bytes")
    print(f"Approx. fragment count: {fragment_count}")

    print("\nPractical note:")
    print("Modern networks often rely on Path MTU Discovery to avoid fragmentation.")


def demonstrate_error_handling() -> None:
    """Show common failures associated with different layers."""

    print_title("19. Troubleshooting by OSI Layer")

    symptoms = {
        1: "No link light / broken cable / radio interference",
        2: "VLAN mismatch / MAC learning issue / switching loop",
        3: "Wrong IP address / missing route / subnet error",
        4: "Blocked port / TCP handshake failure / retransmissions",
        5: "Broken session state / expired session",
        6: "TLS failure / encoding mismatch / certificate problem",
        7: "HTTP error / DNS application failure / invalid request",
    }

    for layer, symptom in symptoms.items():
        print(f"L{layer} {LAYER_NAMES[OSILayer(layer)]:<14}: {symptom}")

    print("\nA useful troubleshooting strategy is to test from lower layers")
    print("toward higher layers while using actual protocol evidence.")


def demonstrate_security_by_layer() -> None:
    """Map representative security controls to OSI layers."""

    print_title("20. Security Considerations by Layer")

    controls = {
        1: "Physical access control, cable protection, radio security",
        2: "802.1X, VLAN controls, switch security, MAC restrictions",
        3: "ACLs, IPsec, routing security, network segmentation",
        4: "Stateful firewalls, port controls, TCP protection",
        5: "Session expiration and session-state validation",
        6: "TLS, certificate validation, cryptographic integrity",
        7: "Authentication, authorization, input validation, application firewalls",
    }

    for layer, control in controls.items():
        print(f"L{layer} {LAYER_NAMES[OSILayer(layer)]:<14}: {control}")

    print("\nSecurity boundaries do not perfectly correspond to OSI layers.")
    print("A production security architecture normally combines controls across layers.")


def demonstrate_performance() -> None:
    """Compare conceptual performance factors across the stack."""

    print_title("21. Performance Considerations")

    factors = [
        ("Physical", "Signal quality, bandwidth, interference"),
        ("Data Link", "Frame overhead, switching, retransmissions"),
        ("Network", "Routing efficiency, packet loss, MTU"),
        ("Transport", "RTT, congestion window, retransmission behavior"),
        ("Session", "Connection/session setup and state"),
        ("Presentation", "Encryption and compression CPU cost"),
        ("Application", "Serialization, database latency, server processing"),
    ]

    for layer, factor in factors:
        print(f"{layer:<15}: {factor}")

    print("\nEnd-to-end latency is the combined result of processing,")
    print("serialization, propagation, queuing, retransmission, and application delays.")


def demonstrate_common_mistakes() -> None:
    """List misconceptions that commonly appear when learning OSI."""

    print_title("22. Common OSI Model Mistakes")

    mistakes = [
        "Treating the OSI model as an exact implementation used by every network stack.",
        "Assuming every protocol belongs to exactly one OSI layer.",
        "Assuming routers only operate at Layer 3 and never inspect higher-layer information.",
        "Confusing a MAC address with an IP address.",
        "Assuming TCP guarantees that an application request itself succeeded.",
        "Assuming ping tests application-layer availability.",
        "Assuming encryption automatically provides authentication without validating credentials/certificates.",
        "Forgetting that real protocols can combine functions associated with multiple OSI layers.",
    ]

    for number, mistake in enumerate(mistakes, start=1):
        print(f"{number}. {mistake}")


def demonstrate_layer_comparison() -> None:
    """Compare OSI with the commonly used TCP/IP model."""

    print_title("23. OSI Model vs TCP/IP Model")

    mapping = [
        ("OSI 7 Application", "TCP/IP Application"),
        ("OSI 6 Presentation", "TCP/IP Application"),
        ("OSI 5 Session", "TCP/IP Application"),
        ("OSI 4 Transport", "TCP/IP Transport"),
        ("OSI 3 Network", "TCP/IP Internet"),
        ("OSI 2 Data Link", "TCP/IP Link / Network Access"),
        ("OSI 1 Physical", "TCP/IP Link / Network Access"),
    ]

    print(f"{'OSI':<30}{'TCP/IP conceptual mapping':<35}")
    print("-" * 65)
    for osi, tcp_ip in mapping:
        print(f"{osi:<30}{tcp_ip:<35}")

    print("\nThe mapping is conceptual rather than a statement that the models are identical.")


def demonstrate_validation() -> None:
    """Show practical validation for IP addresses and ports."""

    print_title("24. Input Validation")

    test_ips = ["192.168.1.10", "10.0.0.1", "999.1.1.1", "2001:db8::1"]
    test_ports = [0, 22, 443, 65535, 65536]

    for text in test_ips:
        try:
            address = ipaddress.ip_address(text)
            print(f"{text:<18} valid IP, IPv{address.version}")
        except ValueError:
            print(f"{text:<18} invalid IP")

    print()
    for port in test_ports:
        valid = 1 <= port <= 65535
        print(f"Port {port:>5}: {'valid' if valid else 'invalid'}")


def demonstrate_packet_loss_and_retransmission() -> None:
    """Simulate deterministic packet loss and TCP-like retransmission."""

    print_title("25. Packet Loss and Retransmission")

    packets = ["SEQ=1", "SEQ=2", "SEQ=3", "SEQ=4"]
    lost_packet = "SEQ=3"

    for packet in packets:
        if packet == lost_packet:
            print(f"{packet}: transmitted -> lost")
        else:
            print(f"{packet}: transmitted -> acknowledged")

    print(f"{lost_packet}: timeout/duplicate-ACK logic -> retransmitted -> acknowledged")
    print("TCP uses retransmission mechanisms as part of reliable byte-stream delivery.")


def demonstrate_design_tradeoffs() -> None:
    """Show why layered architectures are useful despite their overhead."""

    print_title("26. Layering: Benefits and Trade-offs")

    benefits = [
        "Separation of concerns",
        "Interoperability through standardized interfaces",
        "Independent protocol evolution",
        "Easier troubleshooting",
        "Modular implementation",
    ]

    tradeoffs = [
        "Additional headers and processing",
        "Abstraction can hide important implementation details",
        "Real protocols may cross conceptual layer boundaries",
        "Repeated functionality can occur at different layers",
    ]

    print("Benefits:")
    for item in benefits:
        print(f"  + {item}")

    print("\nTrade-offs:")
    for item in tradeoffs:
        print(f"  - {item}")


def run_integrated_scenario() -> None:
    """Walk through a complete web request from client to server."""

    print_title("27. Integrated Scenario: Opening an HTTPS Website")

    steps = [
        (7, "Browser creates an HTTP request."),
        (6, "TLS encrypts the application communication."),
        (5, "Session state is maintained as required by the stack."),
        (4, "TCP establishes a reliable transport connection to port 443."),
        (3, "IP addresses identify the source and destination endpoints."),
        (2, "Ethernet/Wi-Fi frames use local-link addressing."),
        (1, "The network interface transmits physical signals."),
        (1, "A remote interface receives the signal."),
        (2, "The remote host validates the link-layer frame."),
        (3, "The remote host processes the IP packet."),
        (4, "The transport layer processes the TCP segment."),
        (6, "TLS processing authenticates/decrypts as appropriate."),
        (7, "The web server processes the HTTP request."),
    ]

    for layer, description in steps:
        print(f"L{layer} {LAYER_NAMES[OSILayer(layer)]:<14} -> {description}")


def run_self_tests() -> None:
    """Basic executable assertions for important concepts."""

    print_title("28. Self-Tests")

    assert ipaddress.ip_address("127.0.0.1").version == 4
    assert ipaddress.ip_address("::1").version == 6
    assert 1 <= 443 <= 65535

    packet = IPPacket(
        source_ip="192.168.1.10",
        destination_ip="203.0.113.10",
        protocol="TCP",
        payload="HTTPS",
        ttl=2,
    )

    assert packet.forward()
    assert not packet.forward()

    network = ipaddress.ip_network("10.20.30.0/24")
    assert ipaddress.ip_address("10.20.30.50") in network

    print("All self-tests passed.")


def main() -> None:
    print_title("OSI MODEL COMPLETE STUDY PROGRAM")
    print("The Open Systems Interconnection model is a seven-layer reference model.")
    print("This program combines conceptual explanations with executable simulations.")

    demonstrate_layer_roles()
    demonstrate_encapsulation()
    demonstrate_addressing()
    demonstrate_ipv4_header()
    demonstrate_tcp_handshake()
    demonstrate_udp_vs_tcp()
    demonstrate_ports()
    demonstrate_arp_concept()
    demonstrate_switching_and_routing()
    demonstrate_dns()
    demonstrate_http_request()
    demonstrate_tls()
    demonstrate_quic()
    simulate_packet_trace()
    demonstrate_subnetting()
    demonstrate_ipv6()
    demonstrate_routing_algorithm()
    demonstrate_mtu_fragmentation_concept()
    demonstrate_error_handling()
    demonstrate_security_by_layer()
    demonstrate_performance()
    demonstrate_common_mistakes()
    demonstrate_layer_comparison()
    demonstrate_validation()
    demonstrate_packet_loss_and_retransmission()
    demonstrate_design_tradeoffs()
    run_integrated_scenario()
    run_self_tests()

    print_title("END OF OSI MODEL STUDY PROGRAM")
    print("All demonstrations completed successfully.")


if __name__ == "__main__":
    main()
