"""
TCP and UDP Networking: A Comprehensive Study Program

This standalone script teaches:
- IP addresses, ports, sockets, and transport-layer concepts
- TCP versus UDP
- TCP connection establishment and the three-way handshake
- TCP reliability, sequencing, acknowledgements, retransmission, flow control,
  congestion control, and connection termination
- UDP datagrams and connectionless communication
- Client/server communication
- Message framing and validation
- Timeouts, retries, checksums, ordering, duplication, and loss
- Practical local networking demonstrations
- A small reliable protocol implemented over UDP
- Performance, security, debugging, and production considerations

The network examples use only Python's standard library.
"""

from __future__ import annotations

import hashlib
import ipaddress
import random
import socket
import struct
import threading
import time
from dataclasses import dataclass
from typing import Optional


# ============================================================================
# 1. FUNDAMENTAL TERMINOLOGY
# ============================================================================

def print_section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def demonstrate_network_identity() -> None:
    print_section("1. NETWORK IDENTITY: IP ADDRESSES, PORTS, AND SOCKETS")

    ipv4 = ipaddress.ip_address("127.0.0.1")
    ipv6 = ipaddress.ip_address("::1")

    print("IPv4 loopback:", ipv4)
    print("IPv6 loopback:", ipv6)

    print(
        """
An IP address identifies a network interface or host at the network layer.
A port identifies a transport-layer endpoint associated with an application.

A useful conceptual model is:

    IP address + transport protocol + port = communication endpoint

Examples:
    192.168.1.20:443/TCP
    192.168.1.20:53/UDP

A socket is an operating-system abstraction through which an application
sends and receives network data.
"""
    )


# ============================================================================
# 2. TCP AND UDP CHARACTERISTICS
# ============================================================================

def compare_tcp_udp() -> None:
    print_section("2. TCP VERSUS UDP")

    characteristics = {
        "Connection": ("Connection-oriented", "Connectionless"),
        "Reliability": ("Reliable byte stream", "Best-effort datagrams"),
        "Ordering": ("Ordered byte stream", "No ordering guarantee"),
        "Retransmission": ("Implemented by TCP", "Not provided by UDP"),
        "Flow control": ("Yes", "No built-in transport flow control"),
        "Congestion control": ("Yes", "No built-in TCP-style mechanism"),
        "Message boundaries": ("Not preserved", "Preserved per datagram"),
        "Typical overhead": ("Higher", "Lower"),
        "Common uses": ("HTTP(S), SSH, databases", "DNS, real-time media, games"),
    }

    print(f"{'Property':<22} {'TCP':<32} UDP")
    print("-" * 78)
    for property_name, (tcp, udp) in characteristics.items():
        print(f"{property_name:<22} {tcp:<32} {udp}")


# ============================================================================
# 3. TCP THREE-WAY HANDSHAKE
# ============================================================================

@dataclass
class TcpSegment:
    source_port: int
    destination_port: int
    sequence_number: int
    acknowledgement_number: int
    syn: bool = False
    ack: bool = False
    fin: bool = False


def simulate_three_way_handshake() -> None:
    print_section("3. TCP THREE-WAY HANDSHAKE")

    client_isn = 1000
    server_isn = 5000

    syn = TcpSegment(
        source_port=40000,
        destination_port=443,
        sequence_number=client_isn,
        acknowledgement_number=0,
        syn=True,
    )

    syn_ack = TcpSegment(
        source_port=443,
        destination_port=40000,
        sequence_number=server_isn,
        acknowledgement_number=client_isn + 1,
        syn=True,
        ack=True,
    )

    ack = TcpSegment(
        source_port=40000,
        destination_port=443,
        sequence_number=client_isn + 1,
        acknowledgement_number=server_isn + 1,
        ack=True,
    )

    print("1. Client -> Server: SYN")
    print("   sequence =", syn.sequence_number)

    print("2. Server -> Client: SYN + ACK")
    print("   sequence =", syn_ack.sequence_number)
    print("   acknowledgement =", syn_ack.acknowledgement_number)

    print("3. Client -> Server: ACK")
    print("   sequence =", ack.sequence_number)
    print("   acknowledgement =", ack.acknowledgement_number)

    print(
        """
Why three messages?

The client communicates an initial sequence number.
The server communicates its own initial sequence number and acknowledges the
client's number.
The client acknowledges the server's number.

The sequence number is not simply a packet counter. TCP uses sequence numbers
to identify positions in the byte stream.

A SYN consumes one sequence-number position, which is why the acknowledgement
of an initial sequence number N is N + 1.
"""
    )


# ============================================================================
# 4. TCP RELIABILITY MODEL
# ============================================================================

@dataclass
class ReliableMessage:
    sequence: int
    payload: bytes


def demonstrate_tcp_reliability() -> None:
    print_section("4. TCP RELIABILITY: SEQUENCES, ACKS, AND RETRANSMISSION")

    messages = [
        ReliableMessage(0, b"Hello "),
        ReliableMessage(6, b"network "),
        ReliableMessage(14, b"world"),
    ]

    print("Sender transmits:")
    for message in messages:
        print(f"  seq={message.sequence:>2} payload={message.payload!r}")

    print("\nSuppose the second segment is lost.")

    print("Receiver accepts seq=0 and acknowledges the next expected byte.")
    print("Receiver does not have the bytes beginning at sequence 6.")
    print("Sender eventually retransmits the missing data.")

    print(
        """
TCP reliability is implemented through mechanisms including:
- Sequence numbers
- Acknowledgements
- Retransmission timers
- Duplicate-ACK processing
- Sliding windows
- Receive-window based flow control
- Congestion-control algorithms

TCP does not make the Internet itself reliable. It implements reliability
above an unreliable packet-delivery network.
"""
    )


# ============================================================================
# 5. TCP BYTE STREAM AND MESSAGE FRAMING
# ============================================================================

def demonstrate_tcp_framing() -> None:
    print_section("5. TCP IS A BYTE STREAM, NOT A MESSAGE QUEUE")

    first_write = b"HELLO"
    second_write = b"WORLD"

    hypothetical_receive = first_write + second_write

    print("Application writes:", first_write)
    print("Application writes:", second_write)
    print("TCP stream contains:", hypothetical_receive)

    print(
        """
A receiver cannot assume that one send() corresponds to one recv().

Possible observations include:
    HELLOWORLD
    HEL
    LOWORLD
    HELLOW
    WORLD

Therefore application protocols often define framing.

Common framing strategies:
1. Fixed-size records
2. Length-prefixed messages
3. Delimiter-terminated messages
4. Structured serialization formats
"""
    )

    payload = b"network-message"
    framed = struct.pack("!I", len(payload)) + payload

    declared_length = struct.unpack("!I", framed[:4])[0]
    recovered_payload = framed[4:4 + declared_length]

    print("Length-prefixed frame:", framed)
    print("Declared payload length:", declared_length)
    print("Recovered payload:", recovered_payload)


# ============================================================================
# 6. UDP DATAGRAMS
# ============================================================================

def demonstrate_udp_datagrams() -> None:
    print_section("6. UDP DATAGRAM COMMUNICATION")

    print(
        """
UDP preserves datagram boundaries.

If an application sends:
    sendto(b"ONE")
    sendto(b"TWO")

the receiver's recvfrom() calls correspond to datagrams rather than an
arbitrary continuous byte stream.

UDP does not guarantee:
- Delivery
- Ordering
- Duplicate suppression
- Retransmission
- Congestion control
- Connection establishment
"""
    )

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(1.0)

        address = receiver.getsockname()

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.sendto(b"ONE", address)
            sender.sendto(b"TWO", address)

        first, source = receiver.recvfrom(2048)
        second, _ = receiver.recvfrom(2048)

        print("First datagram:", first, "from", source)
        print("Second datagram:", second)


# ============================================================================
# 7. TCP LOCAL CLIENT/SERVER
# ============================================================================

def run_tcp_server(server_ready: threading.Event, port_holder: list[int]) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        # SO_REUSEADDR helps development servers restart cleanly after a
        # previous connection has entered a TCP closing state.
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)

        port_holder.append(server.getsockname()[1])
        server_ready.set()

        connection, address = server.accept()

        with connection:
            print("TCP server accepted:", address)
            connection.settimeout(2.0)

            data = connection.recv(4096)
            response = b"TCP server received: " + data
            connection.sendall(response)


def demonstrate_tcp_socket() -> None:
    print_section("7. EXECUTABLE TCP CLIENT/SERVER EXAMPLE")

    ready = threading.Event()
    port_holder: list[int] = []

    server_thread = threading.Thread(
        target=run_tcp_server,
        args=(ready, port_holder),
        daemon=True,
    )
    server_thread.start()

    if not ready.wait(timeout=2):
        raise RuntimeError("TCP server did not become ready")

    with socket.create_connection(("127.0.0.1", port_holder[0]), timeout=2) as client:
        client.sendall(b"Hello TCP")
        response = client.recv(4096)
        print("Client received:", response)

    server_thread.join(timeout=2)


# ============================================================================
# 8. UDP CLIENT/SERVER
# ============================================================================

def demonstrate_udp_socket() -> None:
    print_section("8. EXECUTABLE UDP CLIENT/SERVER EXAMPLE")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind(("127.0.0.1", 0))
        server.settimeout(2)
        address = server.getsockname()

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(2)
            client.sendto(b"Hello UDP", address)

            message, client_address = server.recvfrom(4096)

            print("Server received:", message)
            print("Client endpoint:", client_address)

            server.sendto(b"UDP response", client_address)

            response, _ = client.recvfrom(4096)
            print("Client received:", response)


# ============================================================================
# 9. TIMEOUTS AND RETRIES
# ============================================================================

def udp_request_with_retry(
    sock: socket.socket,
    server_address: tuple[str, int],
    payload: bytes,
    attempts: int = 3,
    timeout: float = 0.25,
) -> Optional[bytes]:
    """
    UDP itself does not provide application-level retries.

    This function demonstrates how an application can add a retry policy.
    In production, retry policies must account for duplicate requests and
    server-side idempotency.
    """
    sock.settimeout(timeout)

    for attempt in range(1, attempts + 1):
        print(f"Attempt {attempt}: sending {payload!r}")
        sock.sendto(payload, server_address)

        try:
            response, _ = sock.recvfrom(4096)
            return response
        except socket.timeout:
            print("  timeout; retrying")

    return None


# ============================================================================
# 10. APPLICATION-LEVEL RELIABILITY OVER UDP
# ============================================================================

MAGIC = b"RUDP"
HEADER_FORMAT = "!4sBIIH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
DATA_TYPE = 1
ACK_TYPE = 2


@dataclass
class RudpPacket:
    packet_type: int
    sequence: int
    payload: bytes = b""

    def encode(self) -> bytes:
        if len(self.payload) > 65535:
            raise ValueError("Payload is too large")

        header = struct.pack(
            HEADER_FORMAT,
            MAGIC,
            self.packet_type,
            self.sequence,
            len(self.payload),
            0,
        )

        checksum = sum(header[:-2] + self.payload) & 0xFFFF

        return (
            header[:-2]
            + struct.pack("!H", checksum)
            + self.payload
        )

    @staticmethod
    def decode(data: bytes) -> "RudpPacket":
        if len(data) < HEADER_SIZE:
            raise ValueError("Packet is shorter than its header")

        magic, packet_type, sequence, length, checksum = struct.unpack(
            HEADER_FORMAT,
            data[:HEADER_SIZE],
        )

        if magic != MAGIC:
            raise ValueError("Invalid protocol identifier")

        payload = data[HEADER_SIZE:]

        if len(payload) != length:
            raise ValueError("Payload length mismatch")

        reconstructed_header = struct.pack(
            HEADER_FORMAT,
            magic,
            packet_type,
            sequence,
            length,
            0,
        )

        calculated = sum(reconstructed_header[:-2] + payload) & 0xFFFF

        if calculated != checksum:
            raise ValueError("Checksum validation failed")

        return RudpPacket(packet_type, sequence, payload)


def demonstrate_reliable_udp_protocol() -> None:
    print_section("10. BUILDING RELIABILITY ON TOP OF UDP")

    packet = RudpPacket(DATA_TYPE, 7, b"Important data")
    encoded = packet.encode()
    decoded = RudpPacket.decode(encoded)

    print("Encoded packet length:", len(encoded))
    print("Decoded sequence:", decoded.sequence)
    print("Decoded payload:", decoded.payload)

    corrupted = bytearray(encoded)
    corrupted[-1] ^= 0xFF

    try:
        RudpPacket.decode(bytes(corrupted))
    except ValueError as error:
        print("Corrupted packet rejected:", error)

    print(
        """
A reliable UDP protocol may add:
- Sequence numbers
- Acknowledgements
- Retransmission timers
- Duplicate detection
- Ordering buffers
- Checksums
- Request identifiers
- Flow control
- Congestion management

At this point the application is rebuilding features that TCP already provides.
That can be appropriate for specialized protocols, but it also introduces
significant design and testing responsibilities.
"""
    )


# ============================================================================
# 11. ORDERING AND DUPLICATE DETECTION
# ============================================================================

def reorder_udp_messages(
    packets: list[tuple[int, bytes]],
) -> list[bytes]:
    """
    Demonstrates an application-level ordering buffer.
    """
    unique_packets: dict[int, bytes] = {}

    for sequence, payload in packets:
        # Keeping only the first packet for a sequence number demonstrates
        # simple duplicate suppression.
        unique_packets.setdefault(sequence, payload)

    return [
        unique_packets[sequence]
        for sequence in sorted(unique_packets)
    ]


def demonstrate_ordering() -> None:
    print_section("11. ORDERING AND DUPLICATE DETECTION")

    received = [
        (2, b"third"),
        (0, b"first"),
        (2, b"duplicate-third"),
        (1, b"second"),
    ]

    ordered = reorder_udp_messages(received)

    print("Received packets:", received)
    print("Ordered unique payloads:", ordered)


# ============================================================================
# 12. CHECKSUMS AND HASHES
# ============================================================================

def demonstrate_integrity() -> None:
    print_section("12. DATA INTEGRITY")

    message = b"transport data"

    digest = hashlib.sha256(message).hexdigest()

    print("SHA-256:", digest)

    print(
        """
A checksum or hash can detect accidental modification.

Integrity is not the same as authenticity.

A plain hash does not prove who created the data. An attacker who can modify
both the data and an ordinary hash can replace both.

Cryptographic authentication normally requires mechanisms such as:
- Message Authentication Codes
- Digital signatures
- Authenticated encryption
- TLS or another secure protocol

TCP checksums and UDP checksums provide transport-level error detection.
They are not substitutes for cryptographic authentication.
"""
    )


# ============================================================================
# 13. PORTS AND SOCKET STATES
# ============================================================================

def demonstrate_ports() -> None:
    print_section("13. PORTS AND CONNECTION IDENTIFICATION")

    print(
        """
A TCP connection is commonly identified by a four-tuple:

    source IP
    source port
    destination IP
    destination port

The transport protocol is also relevant when distinguishing TCP and UDP.

A server generally binds a known local port.
A client commonly receives an ephemeral source port from the operating system.

TCP servers often use:
    socket()
    bind()
    listen()
    accept()

TCP clients commonly use:
    socket()
    connect()

UDP applications commonly use:
    socket()
    bind()          # if they need a known local port
    sendto()
    recvfrom()
"""
    )


# ============================================================================
# 14. TCP CONNECTION TERMINATION
# ============================================================================

def demonstrate_tcp_termination() -> None:
    print_section("14. TCP CONNECTION TERMINATION")

    print(
        """
TCP connection termination normally uses FIN and ACK signaling.

A simplified exchange is:

    Endpoint A -> FIN
    Endpoint B -> ACK
    Endpoint B -> FIN
    Endpoint A -> ACK

TCP is full-duplex, so each direction can be closed independently.

TIME_WAIT is an important TCP state associated with active connection
termination. It helps prevent delayed segments from an older connection from
being confused with a later connection using the same endpoint combination.
"""
    )


# ============================================================================
# 15. FLOW CONTROL AND CONGESTION CONTROL
# ============================================================================

def demonstrate_flow_and_congestion() -> None:
    print_section("15. FLOW CONTROL VERSUS CONGESTION CONTROL")

    receiver_window = 32_768
    congestion_window = 16_384

    effective_window = min(receiver_window, congestion_window)

    print("Receiver advertised window:", receiver_window)
    print("Congestion window:", congestion_window)
    print("Simplified effective sending limit:", effective_window)

    print(
        """
Flow control protects a receiver from being overwhelmed.

Congestion control protects the network from excessive traffic.

They solve different problems.

TCP implementations use mechanisms such as:
- Receive windows
- Slow start
- Congestion avoidance
- Fast retransmit
- Fast recovery
- Modern congestion-control algorithms

The exact algorithms and behavior depend on the operating system and TCP
implementation.
"""
    )


# ============================================================================
# 16. NAGLE, LATENCY, AND SMALL MESSAGES
# ============================================================================

def demonstrate_latency_tradeoffs() -> None:
    print_section("16. LATENCY AND THROUGHPUT TRADE-OFFS")

    message_sizes = [20, 100, 1000, 10000]

    for size in message_sizes:
        print(f"Application payload: {size:>5} bytes")

    print(
        """
Small frequent TCP writes can interact with buffering and algorithms such as
Nagle's algorithm. Applications sensitive to latency sometimes configure
TCP_NODELAY, but disabling buffering can increase packet overhead.

The correct choice depends on:
- Message frequency
- Payload size
- Latency requirements
- Network characteristics
- Receiver behavior
- Protocol design
"""
    )


# ============================================================================
# 17. SECURITY CONSIDERATIONS
# ============================================================================

def demonstrate_security() -> None:
    print_section("17. SECURITY CONSIDERATIONS")

    print(
        """
Transport protocols do not automatically make application data confidential.

TCP and UDP alone do not provide encryption.

Important security issues include:
- Port scanning
- Denial-of-service attacks
- UDP amplification risks
- Spoofed source addresses
- Resource exhaustion
- Malformed packet handling
- Authentication failures
- Replay attacks
- Application-layer injection
- Unbounded message sizes

Secure systems should:
- Validate all received input.
- Enforce maximum packet and message sizes.
- Apply timeouts.
- Limit concurrent connections.
- Authenticate sensitive operations.
- Use TLS for TCP-based application protocols when appropriate.
- Use an authenticated secure transport when UDP semantics are required.
- Avoid treating source IP addresses as reliable identity.
"""
    )


# ============================================================================
# 18. DEBUGGING AND OBSERVABILITY
# ============================================================================

def demonstrate_debugging() -> None:
    print_section("18. NETWORK DEBUGGING")

    print(
        """
Useful observations when debugging transport communication:

1. Is the server listening?
2. Is the correct IP address being used?
3. Is the correct port being used?
4. Is a firewall blocking traffic?
5. Is the socket bound to the expected interface?
6. Are packets reaching the destination?
7. Is the application reading all available TCP bytes?
8. Are UDP packets being lost or rejected?
9. Are timeouts too aggressive?
10. Are protocol messages correctly framed?

Tools commonly used by network engineers include socket inspection utilities,
packet analyzers, logs, metrics, and packet-capture systems.

A packet capture can reveal TCP SYN, SYN-ACK, ACK, retransmissions, resets,
FIN packets, UDP datagrams, and timing information.
"""
    )


# ============================================================================
# 19. PERFORMANCE MEASUREMENT
# ============================================================================

def measure_local_udp_round_trip() -> None:
    print_section("19. SIMPLE UDP ROUND-TRIP MEASUREMENT")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind(("127.0.0.1", 0))
        server.settimeout(1)
        address = server.getsockname()

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(1)

            start = time.perf_counter()
            client.sendto(b"ping", address)
            data, source = server.recvfrom(1024)
            server.sendto(data, source)
            client.recvfrom(1024)
            elapsed = time.perf_counter() - start

            print(f"Local UDP round-trip time: {elapsed * 1000:.3f} ms")

    print(
        """
A localhost measurement is not representative of Internet latency.
Real networks add propagation, transmission, queuing, routing, congestion,
wireless interference, firewall processing, and other effects.
"""
    )


# ============================================================================
# 20. EDGE CASES
# ============================================================================

def demonstrate_edge_cases() -> None:
    print_section("20. IMPORTANT EDGE CASES")

    cases = [
        ("Empty UDP payload", b""),
        ("One-byte payload", b"x"),
        ("Large ordinary payload", b"x" * 1024),
    ]

    for name, payload in cases:
        print(name, "->", len(payload), "bytes")

    print(
        """
Important edge cases include:
- Empty messages
- Partial TCP reads
- Connection closed while reading
- Connection reset
- Timeout
- Duplicate UDP datagrams
- Out-of-order UDP datagrams
- Oversized datagrams
- Invalid protocol fields
- Corrupted payloads
- Unexpected peer termination
- Port already in use
- DNS resolution failure
- IPv4 versus IPv6 differences

A robust protocol defines expected behavior for each relevant failure mode.
"""
    )


# ============================================================================
# 21. PRACTICAL DESIGN COMPARISON
# ============================================================================

def compare_use_cases() -> None:
    print_section("21. PRACTICAL TCP AND UDP USE CASES")

    examples = {
        "Web page delivery": "TCP is historically common; modern HTTP/3 uses QUIC over UDP.",
        "SSH": "TCP",
        "Traditional DNS queries": "UDP is common, with TCP also used when required.",
        "Real-time voice": "UDP-based transports are common because timely delivery can matter more than retransmission.",
        "Database sessions": "TCP is common because ordered reliable delivery is useful.",
        "Broadcast/discovery": "UDP is often useful because it supports datagram-oriented communication.",
    }

    for application, transport in examples.items():
        print(f"{application:<28} {transport}")


# ============================================================================
# 22. PRODUCTION SOCKET PRACTICES
# ============================================================================

def production_practices() -> None:
    print_section("22. PRODUCTION SOCKET DESIGN")

    print(
        """
Production systems should consider:

TCP:
- Socket and connection timeouts
- Connection limits
- Backpressure
- Partial reads and writes
- Graceful shutdown
- Connection pooling where appropriate
- TLS configuration
- Keepalive strategy
- Resource cleanup
- Protocol framing
- Logging and metrics

UDP:
- Datagram-size limits
- Timeouts
- Retry policy
- Duplicate handling
- Ordering requirements
- Rate limiting
- Authentication
- Replay protection
- Congestion behavior
- Amplification prevention

For both:
- Validate all untrusted data.
- Avoid unbounded memory allocation.
- Close resources reliably.
- Define protocol versioning.
- Make failures observable.
- Test under packet loss, delay, duplication, and reordering.
"""
    )


# ============================================================================
# 23. MINI EXPERIMENT: SIMULATED UDP LOSS
# ============================================================================

def simulate_packet_loss() -> None:
    print_section("23. SIMULATING UDP PACKET LOSS")

    random.seed(7)

    packets = list(range(1, 11))
    loss_probability = 0.30

    delivered = []
    lost = []

    for sequence in packets:
        if random.random() < loss_probability:
            lost.append(sequence)
        else:
            delivered.append(sequence)

    print("Sent:", packets)
    print("Delivered:", delivered)
    print("Lost:", lost)

    print(
        """
This simulation illustrates why an application using UDP cannot assume that
every sendto() results in a successful receivefrom().

The operating system may successfully hand a datagram to the network stack
without providing an end-to-end delivery guarantee to the application.
"""
    )


# ============================================================================
# 24. MAIN STUDY PROGRAM
# ============================================================================

def main() -> None:
    demonstrate_network_identity()
    compare_tcp_udp()
    simulate_three_way_handshake()
    demonstrate_tcp_reliability()
    demonstrate_tcp_framing()
    demonstrate_udp_datagrams()
    demonstrate_tcp_socket()
    demonstrate_udp_socket()
    demonstrate_reliable_udp_protocol()
    demonstrate_ordering()
    demonstrate_integrity()
    demonstrate_ports()
    demonstrate_tcp_termination()
    demonstrate_flow_and_congestion()
    demonstrate_latency_tradeoffs()
    demonstrate_security()
    demonstrate_debugging()
    measure_local_udp_round_trip()
    demonstrate_edge_cases()
    compare_use_cases()
    production_practices()
    simulate_packet_loss()

    print_section("STUDY PROGRAM COMPLETE")
    print(
        "The examples covered TCP connection establishment, reliability, "
        "ports, sockets, UDP datagrams, and application-level reliability."
    )


if __name__ == "__main__":
    main()
