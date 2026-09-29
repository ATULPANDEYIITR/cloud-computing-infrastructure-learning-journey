Routing and NAT: Routing Tables, Gateways, Routers, NAT, and
Private-to-Public Communication

This standalone study program progresses from networking fundamentals to
routing-table inspection, longest-prefix matching, default gateways,
router forwarding, NAT/PAT, traceroute concepts, and a small end-to-end
network simulation.

The demonstrations intentionally use simulated addresses and packets so the
program remains safe, portable, and executable without administrative access
or special networking privileges.

Real-system commands discussed and optionally inspected:
    ip route
    ip addr
    traceroute
    tracepath
    ping

Run:
    python routing_nat.py

The program uses only the Python standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv4Network, ip_address, ip_network
from collections import defaultdict, deque
from typing import Optional
import argparse
import random
import socket
import subprocess
import sys
import time


# ============================================================================
# 1. FUNDAMENTAL NETWORKING CONCEPTS
# ============================================================================

def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def subsection(title: str) -> None:
    print(f"\n--- {title} ---")


def explain_address(address: str) -> None:
    ip = IPv4Address(address)
    print(f"Address:          {ip}")
    print(f"Integer form:     {int(ip)}")
    print(f"Packed form:      {ip.packed.hex()}")
    print(f"Private address:  {ip.is_private}")
    print(f"Loopback:         {ip.is_loopback}")
    print(f"Multicast:        {ip.is_multicast}")


def demo_addressing() -> None:
    section("1. IP Addressing and Networks")

    examples = [
        ("192.168.1.10", "192.168.1.0/24"),
        ("10.20.30.40", "10.0.0.0/8"),
        ("172.16.5.20", "172.16.0.0/12"),
        ("8.8.8.8", "0.0.0.0/0"),
    ]

    for address, network in examples:
        ip = IPv4Address(address)
        net = IPv4Network(network)
        print(
            f"{ip:<15} belongs to {net:<18} = "
            f"{ip in net}"
        )

    subsection("Private IPv4 ranges")
    private_ranges = [
        IPv4Network("10.0.0.0/8"),
        IPv4Network("172.16.0.0/12"),
        IPv4Network("192.168.0.0/16"),
    ]
    for network in private_ranges:
        print(f"{network}: RFC 1918 private address space")

    subsection("Host, network, and broadcast concepts")
    network = IPv4Network("192.168.10.0/24")
    print(f"Network address:   {network.network_address}")
    print(f"First usable:      {network.network_address + 1}")
    print(f"Last usable:       {network.broadcast_address - 1}")
    print(f"Broadcast address: {network.broadcast_address}")
    print(f"Prefix length:     {network.prefixlen}")
    print(f"Usable hosts:      {network.num_addresses - 2}")

    subsection("Important distinction")
    print(
        "An IP address identifies a Layer-3 interface/address. A subnet "
        "describes which addresses are considered directly reachable through "
        "that Layer-3 network. A gateway is normally the next-hop router "
        "used when a destination is outside the local subnet."
    )


# ============================================================================
# 2. SUBNET MEMBERSHIP AND LONGEST-PREFIX MATCHING
# ============================================================================

@dataclass(frozen=True)
class Route:
    network: IPv4Network
    next_hop: Optional[IPv4Address]
    interface: str
    metric: int = 100
    description: str = ""

    @property
    def prefix_length(self) -> int:
        return self.network.prefixlen


def route_sort_key(route: Route) -> tuple[int, int]:
    # Longest prefix wins. If prefix lengths tie, lower metric wins.
    return (-route.prefix_length, route.metric)


def choose_route(routes: list[Route], destination: str) -> Optional[Route]:
    destination_ip = IPv4Address(destination)
    matches = [route for route in routes if destination_ip in route.network]

    if not matches:
        return None

    matches.sort(key=route_sort_key)
    return matches[0]


def demo_longest_prefix() -> None:
    section("2. Routing Tables and Longest-Prefix Matching")

    routes = [
        Route(
            IPv4Network("0.0.0.0/0"),
            IPv4Address("192.168.1.1"),
            "eth0",
            100,
            "default route",
        ),
        Route(
            IPv4Network("10.0.0.0/8"),
            IPv4Address("192.168.1.254"),
            "eth1",
            100,
            "private enterprise network",
        ),
        Route(
            IPv4Network("10.10.0.0/16"),
            IPv4Address("192.168.1.253"),
            "eth2",
            100,
            "regional network",
        ),
        Route(
            IPv4Network("10.10.20.0/24"),
            IPv4Address("192.168.1.252"),
            "eth3",
            50,
            "specific application subnet",
        ),
    ]

    print("Simulated routing table:")
    for route in routes:
        print(
            f"{str(route.network):<18} "
            f"via {str(route.next_hop):<15} "
            f"dev {route.interface:<5} "
            f"metric={route.metric:<3} "
            f"{route.description}"
        )

    for destination in [
        "10.10.20.55",
        "10.10.40.10",
        "10.50.1.1",
        "8.8.8.8",
    ]:
        selected = choose_route(routes, destination)
        if selected:
            print(
                f"Destination {destination:<15} -> "
                f"{selected.network} via {selected.next_hop} "
                f"dev {selected.interface}"
            )
        else:
            print(f"Destination {destination:<15} -> no route")

    print(
        "\nThe important rule is longest-prefix match: /24 is more specific "
        "than /16, /16 is more specific than /8, and /8 is more specific "
        "than the default /0 route."
    )


# ============================================================================
# 3. ROUTER FORWARDING MODEL
# ============================================================================

@dataclass
class Packet:
    source_ip: IPv4Address
    destination_ip: IPv4Address
    source_port: Optional[int] = None
    destination_port: Optional[int] = None
    protocol: str = "TCP"
    ttl: int = 64
    payload: str = ""

    def clone(self) -> "Packet":
        return Packet(
            self.source_ip,
            self.destination_ip,
            self.source_port,
            self.destination_port,
            self.protocol,
            self.ttl,
            self.payload,
        )

    def summary(self) -> str:
        ports = ""
        if self.source_port is not None and self.destination_port is not None:
            ports = f":{self.source_port} -> :{self.destination_port}"
        return (
            f"{self.protocol} {self.source_ip}{ports} -> "
            f"{self.destination_ip} TTL={self.ttl}"
        )


class Router:
    def __init__(self, name: str):
        self.name = name
        self.routes: list[Route] = []
        self.forwarding_enabled = True

    def add_route(
        self,
        network: str,
        next_hop: Optional[str],
        interface: str,
        metric: int = 100,
        description: str = "",
    ) -> None:
        self.routes.append(
            Route(
                IPv4Network(network),
                IPv4Address(next_hop) if next_hop else None,
                interface,
                metric,
                description,
            )
        )

    def lookup(self, destination: IPv4Address) -> Optional[Route]:
        return choose_route(self.routes, str(destination))

    def forward(self, packet: Packet) -> Optional[Route]:
        if not self.forwarding_enabled:
            raise RuntimeError(f"{self.name}: IP forwarding is disabled")

        if packet.ttl <= 1:
            raise RuntimeError(f"{self.name}: TTL expired")

        packet.ttl -= 1
        route = self.lookup(packet.destination_ip)

        if route is None:
            raise RuntimeError(
                f"{self.name}: no route to {packet.destination_ip}"
            )

        return route

    def display_table(self) -> None:
        print(f"\nRouting table for {self.name}")
        for route in sorted(self.routes, key=route_sort_key):
            next_hop = str(route.next_hop) if route.next_hop else "direct"
            print(
                f"{route.network:<18} "
                f"via {next_hop:<15} "
                f"dev {route.interface:<8} "
                f"metric {route.metric}"
            )


def demo_router() -> None:
    section("3. Router Forwarding")

    router = Router("R1")
    router.add_route(
        "192.168.10.0/24",
        None,
        "lan0",
        0,
        "directly connected LAN",
    )
    router.add_route(
        "192.168.20.0/24",
        None,
        "lan1",
        0,
        "directly connected server LAN",
    )
    router.add_route(
        "0.0.0.0/0",
        "192.168.10.254",
        "wan0",
        100,
        "upstream/default gateway",
    )

    router.display_table()

    packet = Packet(
        IPv4Address("192.168.10.50"),
        IPv4Address("192.168.20.80"),
        50000,
        443,
        "TCP",
    )

    print(f"\nBefore forwarding: {packet.summary()}")
    selected = router.forward(packet)
    print(
        f"Selected route: {selected.network}, "
        f"interface={selected.interface}"
    )
    print(f"After forwarding:  {packet.summary()}")

    print(
        "\nA router does not normally forward a packet simply because it "
        "knows an IP address. It consults its routing information, chooses "
        "the best matching route, decrements IPv4 TTL, and sends the packet "
        "toward the selected next hop/interface."
    )


# ============================================================================
# 4. DEFAULT GATEWAY
# ============================================================================

@dataclass
class Host:
    name: str
    address: IPv4Address
    network: IPv4Network
    gateway: Optional[IPv4Address]

    def needs_gateway(self, destination: IPv4Address) -> bool:
        return destination not in self.network

    def next_hop(self, destination: IPv4Address) -> Optional[IPv4Address]:
        if destination in self.network:
            return destination
        return self.gateway


def demo_gateway() -> None:
    section("4. Default Gateway")

    host = Host(
        "client",
        IPv4Address("192.168.1.50"),
        IPv4Network("192.168.1.0/24"),
        IPv4Address("192.168.1.1"),
    )

    destinations = [
        IPv4Address("192.168.1.75"),
        IPv4Address("192.168.2.75"),
        IPv4Address("8.8.8.8"),
    ]

    for destination in destinations:
        if host.needs_gateway(destination):
            print(
                f"{destination}: outside {host.network}; "
                f"send to default gateway {host.gateway}"
            )
        else:
            print(
                f"{destination}: directly reachable on {host.network}; "
                f"gateway is not required for Layer-3 routing"
            )

    print(
        "\nThe default gateway is not necessarily an Internet router. "
        "It is the host's configured next-hop router for destinations that "
        "do not match a more specific local route."
    )


# ============================================================================
# 5. NAT FUNDAMENTALS
# ============================================================================

@dataclass(frozen=True)
class NatKey:
    private_ip: IPv4Address
    private_port: int
    remote_ip: IPv4Address
    remote_port: int
    protocol: str


@dataclass
class NatMapping:
    private_ip: IPv4Address
    private_port: int
    public_ip: IPv4Address
    public_port: int
    remote_ip: IPv4Address
    remote_port: int
    protocol: str
    created_at: float = field(default_factory=time.time)
    packets: int = 0

    def private_endpoint(self) -> str:
        return f"{self.private_ip}:{self.private_port}"

    def public_endpoint(self) -> str:
        return f"{self.public_ip}:{self.public_port}"


class PortAddressTranslation:
    """
    Simplified PAT/NAPT implementation.

    Real NAT implementations maintain substantially more state and protocol-
    specific behavior. This educational version models the central idea:
    multiple private flows can share one public IPv4 address by using distinct
    source ports.
    """

    def __init__(
        self,
        public_ip: str,
        port_start: int = 40000,
        port_end: int = 49999,
    ):
        self.public_ip = IPv4Address(public_ip)
        self.port_start = port_start
        self.port_end = port_end
        self.next_port = port_start
        self.outbound: dict[NatKey, NatMapping] = {}
        self.inbound: dict[tuple[str, int, str], NatMapping] = {}

    def _allocate_port(self) -> int:
        attempts = self.port_end - self.port_start + 1

        for _ in range(attempts):
            port = self.next_port
            self.next_port += 1

            if self.next_port > self.port_end:
                self.next_port = self.port_start

            if (
                self.public_ip, port, "TCP"
            ) not in [
                (m.public_ip, m.public_port, m.protocol)
                for m in self.outbound.values()
            ]:
                return port

        raise RuntimeError("NAT port pool exhausted")

    def translate_outbound(self, packet: Packet) -> Packet:
        if packet.source_port is None or packet.destination_port is None:
            raise ValueError("PAT requires transport-layer ports")

        key = NatKey(
            packet.source_ip,
            packet.source_port,
            packet.destination_ip,
            packet.destination_port,
            packet.protocol,
        )

        mapping = self.outbound.get(key)

        if mapping is None:
            public_port = self._allocate_port()
            mapping = NatMapping(
                packet.source_ip,
                packet.source_port,
                self.public_ip,
                public_port,
                packet.destination_ip,
                packet.destination_port,
                packet.protocol,
            )
            self.outbound[key] = mapping
            self.inbound[
                (
                    str(self.public_ip),
                    public_port,
                    packet.protocol,
                )
            ] = mapping

        mapping.packets += 1

        translated = packet.clone()
        translated.source_ip = self.public_ip
        translated.source_port = mapping.public_port
        return translated

    def translate_inbound(self, packet: Packet) -> Packet:
        if packet.destination_port is None:
            raise ValueError("Inbound PAT requires destination port")

        key = (
            str(packet.destination_ip),
            packet.destination_port,
            packet.protocol,
        )

        mapping = self.inbound.get(key)

        if mapping is None:
            raise RuntimeError("No matching NAT state for inbound packet")

        translated = packet.clone()
        translated.destination_ip = mapping.private_ip
        translated.destination_port = mapping.private_port
        return translated

    def display(self) -> None:
        print("\nNAT translation table")
        if not self.outbound:
            print("(empty)")
            return

        for mapping in self.outbound.values():
            print(
                f"{mapping.private_endpoint():<22} -> "
                f"{mapping.public_endpoint():<22} -> "
                f"{mapping.remote_ip}:{mapping.remote_port} "
                f"{mapping.protocol} packets={mapping.packets}"
            )


def demo_nat() -> None:
    section("5. NAT and PAT")

    nat = PortAddressTranslation("203.0.113.10")

    private_packets = [
        Packet(
            IPv4Address("192.168.1.10"),
            IPv4Address("93.184.216.34"),
            51000,
            443,
            "TCP",
        ),
        Packet(
            IPv4Address("192.168.1.11"),
            IPv4Address("93.184.216.34"),
            51001,
            443,
            "TCP",
        ),
        Packet(
            IPv4Address("192.168.1.10"),
            IPv4Address("142.250.72.14"),
            51002,
            443,
            "TCP",
        ),
    ]

    translated_packets = []

    for packet in private_packets:
        translated = nat.translate_outbound(packet)
        translated_packets.append(translated)

        print("Before NAT :", packet.summary())
        print("After NAT  :", translated.summary())
        print()

    nat.display()

    response = Packet(
        IPv4Address("93.184.216.34"),
        translated_packets[0].source_ip,
        443,
        translated_packets[0].source_port,
        "TCP",
    )

    restored = nat.translate_inbound(response)
    print("\nInbound response before reverse NAT:")
    print(response.summary())
    print("Inbound response after reverse NAT:")
    print(restored.summary())

    print(
        "\nPAT allows many private clients to share one public IPv4 address "
        "by distinguishing simultaneous flows using transport-layer ports."
    )


# ============================================================================
# 6. STATIC NAT, DYNAMIC NAT, PAT, AND RELATED CONCEPTS
# ============================================================================

def explain_nat_types() -> None:
    section("6. NAT Classifications")

    rows = [
        (
            "Static NAT",
            "One private address maps consistently to one public address",
            "Publishing an internal server through a stable address",
        ),
        (
            "Dynamic NAT",
            "Private addresses temporarily use addresses from a public pool",
            "Organizations with a pool of public IPv4 addresses",
        ),
        (
            "PAT/NAPT",
            "Many private flows share public addresses using port mappings",
            "Typical home/office IPv4 Internet access",
        ),
        (
            "DNAT",
            "Destination address/port is rewritten",
            "Port forwarding and inbound publishing",
        ),
        (
            "SNAT",
            "Source address/port is rewritten",
            "Outbound Internet access",
        ),
    ]

    for name, mechanism, use_case in rows:
        print(f"{name:<14} | {mechanism}")
        print(f"{'':14} | Use: {use_case}")

    print(
        "\nNAT is an address-translation mechanism, not a replacement for "
        "routing. A NAT gateway still needs routes to determine where packets "
        "should travel."
    )


# ============================================================================
# 7. PRIVATE-TO-PUBLIC END-TO-END SIMULATION
# ============================================================================

@dataclass
class SimulatedLink:
    left: str
    right: str
    network: IPv4Network


class NetworkSimulation:
    def __init__(self):
        self.routers: dict[str, Router] = {}
        self.hosts: dict[str, Host] = {}
        self.nat: Optional[PortAddressTranslation] = None
        self.links: list[SimulatedLink] = []

    def add_router(self, router: Router) -> None:
        self.routers[router.name] = router

    def add_host(self, host: Host) -> None:
        self.hosts[host.name] = host

    def add_link(self, left: str, right: str, network: str) -> None:
        self.links.append(
            SimulatedLink(left, right, IPv4Network(network))
        )

    def display_topology(self) -> None:
        print("\nTopology:")
        for link in self.links:
            print(f"{link.left} <-> {link.right} [{link.network}]")


def build_private_public_network() -> NetworkSimulation:
    simulation = NetworkSimulation()

    client = Host(
        "LAN-Client",
        IPv4Address("192.168.50.10"),
        IPv4Network("192.168.50.0/24"),
        IPv4Address("192.168.50.1"),
    )

    edge = Router("Edge-Router")
    edge.add_route(
        "192.168.50.0/24",
        None,
        "lan",
        0,
        "private LAN",
    )
    edge.add_route(
        "203.0.113.0/30",
        None,
        "wan",
        0,
        "ISP transit",
    )
    edge.add_route(
        "0.0.0.0/0",
        "203.0.113.1",
        "wan",
        10,
        "Internet default route",
    )

    isp = Router("ISP-Router")
    isp.add_route(
        "203.0.113.0/30",
        None,
        "customer",
        0,
        "customer link",
    )
    isp.add_route(
        "198.51.100.0/24",
        None,
        "internet",
        0,
        "example Internet network",
    )

    internet_server = Host(
        "Internet-Server",
        IPv4Address("198.51.100.20"),
        IPv4Network("198.51.100.0/24"),
        IPv4Address("198.51.100.1"),
    )

    simulation.add_host(client)
    simulation.add_host(internet_server)
    simulation.add_router(edge)
    simulation.add_router(isp)
    simulation.nat = PortAddressTranslation("203.0.113.2")
    simulation.add_link(
        "LAN-Client",
        "Edge-Router",
        "192.168.50.0/24",
    )
    simulation.add_link(
        "Edge-Router",
        "ISP-Router",
        "203.0.113.0/30",
    )
    simulation.add_link(
        "ISP-Router",
        "Internet-Server",
        "198.51.100.0/24",
    )

    return simulation


def demo_end_to_end() -> None:
    section("7. Private-to-Public Communication")

    simulation = build_private_public_network()
    simulation.display_topology()

    assert simulation.nat is not None

    client = simulation.hosts["LAN-Client"]
    server = simulation.hosts["Internet-Server"]

    packet = Packet(
        client.address,
        server.address,
        52000,
        443,
        "TCP",
        ttl=8,
        payload="HTTPS request",
    )

    print("\nStage 1: application host creates a packet")
    print(packet.summary())

    print("\nStage 2: client determines next hop")
    print(f"Destination {server.address} is outside {client.network}")
    print(f"Client sends packet to gateway {client.gateway}")

    print("\nStage 3: edge router performs NAT")
    translated = simulation.nat.translate_outbound(packet)
    print(f"Before NAT: {packet.summary()}")
    print(f"After NAT:  {translated.summary()}")

    print("\nStage 4: edge router selects its default route")
    edge = simulation.routers["Edge-Router"]
    route = edge.lookup(translated.destination_ip)
    if route is None:
        raise RuntimeError("Edge router has no route to Internet")
    print(
        f"Route: {route.network} via {route.next_hop} "
        f"dev {route.interface}"
    )

    print("\nStage 5: ISP router receives the public packet")
    isp = simulation.routers["ISP-Router"]
    isp_route = isp.lookup(translated.destination_ip)
    if isp_route is None:
        raise RuntimeError("ISP router cannot reach server network")
    print(
        f"ISP route: {isp_route.network} "
        f"dev {isp_route.interface}"
    )

    print("\nStage 6: destination server receives the packet")
    print(
        f"{server.name} receives traffic addressed to "
        f"{translated.destination_ip}:{translated.destination_port}"
    )

    print("\nStage 7: server response returns to public NAT endpoint")
    response = Packet(
        server.address,
        translated.source_ip,
        443,
        translated.source_port,
        "TCP",
        ttl=8,
        payload="HTTPS response",
    )
    print(f"Before reverse NAT: {response.summary()}")

    restored = simulation.nat.translate_inbound(response)
    print(f"After reverse NAT:  {restored.summary()}")

    print(
        "\nThe complete logical path is:\n"
        "private client -> default gateway -> NAT -> ISP -> Internet "
        "server -> ISP -> public NAT address -> reverse NAT -> private client"
    )


# ============================================================================
# 8. TTL AND TRACEROUTE
# ============================================================================

@dataclass
class Hop:
    address: IPv4Address
    name: str
    delay_ms: float


def simulate_traceroute(
    hops: list[Hop],
    destination: IPv4Address,
    max_hops: int = 30,
) -> list[str]:
    """
    Educational traceroute simulation.

    Traditional IPv4 traceroute sends probes with TTL values 1, 2, 3, ...
    Routers decrement TTL. When TTL reaches zero, the router commonly sends
    ICMP Time Exceeded. The final destination eventually responds differently
    when the probe reaches it.

    Real traceroute implementations vary by OS and may use UDP, ICMP Echo,
    or TCP probes.
    """
    results = []

    for ttl in range(1, max_hops + 1):
        if ttl <= len(hops):
            hop = hops[ttl - 1]
            if ttl < len(hops):
                results.append(
                    f"{ttl:2d}  {hop.address:<15} "
                    f"{hop.delay_ms:6.2f} ms  {hop.name} "
                    "(TTL expired -> ICMP Time Exceeded)"
                )
            else:
                results.append(
                    f"{ttl:2d}  {hop.address:<15} "
                    f"{hop.delay_ms:6.2f} ms  {hop.name} "
                    "(destination reached)"
                )
                break
        else:
            results.append(f"{ttl:2d}  * * *  no response")
            break

    return results


def demo_traceroute() -> None:
    section("8. Traceroute and TTL")

    hops = [
        Hop(IPv4Address("192.168.50.1"), "Edge-Router", 1.2),
        Hop(IPv4Address("203.0.113.1"), "ISP-Router", 8.7),
        Hop(IPv4Address("198.51.100.1"), "Transit-Router", 17.3),
        Hop(IPv4Address("198.51.100.20"), "Internet-Server", 22.4),
    ]

    print("Simulated traceroute:")
    for line in simulate_traceroute(
        hops,
        IPv4Address("198.51.100.20"),
    ):
        print(line)

    print(
        "\nTraceroute is an observation technique, not a routing-table "
        "display. It infers the path from probe responses. Firewalls, ACLs, "
        "load balancing, asymmetric paths, rate limiting, and routers that "
        "do not return TTL-expired responses can make traceroute incomplete."
    )


# ============================================================================
# 9. REAL SYSTEM COMMANDS
# ============================================================================

def run_command(command: list[str], timeout: int = 5) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", f"Command not found: {command[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out: {' '.join(command)}"


def show_real_routing_table() -> None:
    section("9. Inspecting a Real Routing Table")

    print("Linux command: ip route")
    print(
        "This section only reads routing information. It does not modify "
        "your network configuration."
    )

    if sys.platform.startswith("linux"):
        code, stdout, stderr = run_command(["ip", "route"])
        if code == 0:
            print("\nCurrent routing table:")
            print(stdout.rstrip())
        else:
            print(f"\nUnable to run ip route: {stderr.strip()}")
    elif sys.platform == "win32":
        print(
            "\nWindows equivalent commands include:\n"
            "  route print\n"
            "  ipconfig\n"
            "  tracert <destination>"
        )
        code, stdout, stderr = run_command(["route", "print"])
        if code == 0:
            print("\nCurrent Windows routing table:")
            print(stdout.rstrip())
        else:
            print(f"\nUnable to run route print: {stderr.strip()}")
    else:
        print(
            "\nFor this operating system, inspect the platform's routing "
            "table using its native network tools."
        )


def show_interface_addresses() -> None:
    section("10. Interface Address Inspection")

    print("Local hostname:", socket.gethostname())

    try:
        addresses = socket.getaddrinfo(
            socket.gethostname(),
            None,
            family=socket.AF_INET,
        )
        unique = sorted({item[4][0] for item in addresses})
        print("IPv4 addresses returned by the local resolver:")
        for address in unique:
            print(f"  {address}")
    except socket.gaierror as exc:
        print(f"Could not resolve local hostname: {exc}")

    print(
        "\nFor complete interface and prefix information on Linux, "
        "ip addr is generally more informative than hostname resolution."
    )


# ============================================================================
# 10. ROUTING PROTOCOL CONCEPTS
# ============================================================================

def explain_routing_protocols() -> None:
    section("11. Static and Dynamic Routing")

    protocols = [
        (
            "Static routing",
            "Administrator explicitly configures routes",
            "Small networks, stable paths, controlled infrastructure",
        ),
        (
            "RIP",
            "Distance-vector routing using hop count",
            "Historical/small-network scenarios; limited scalability",
        ),
        (
            "OSPF",
            "Link-state interior gateway protocol",
            "Enterprise and data-center internal routing",
        ),
        (
            "IS-IS",
            "Link-state interior gateway protocol",
            "Large service-provider and infrastructure networks",
        ),
        (
            "BGP",
            "Path-vector inter-domain routing",
            "Internet-scale routing between autonomous systems",
        ),
    ]

    for name, mechanism, use in protocols:
        print(f"{name:<18} {mechanism}")
        print(f"{'':18} Typical use: {use}\n")

    print(
        "A routing table is the forwarding result used by a device. "
        "A routing protocol is one possible mechanism for learning routes. "
        "They are related but are not the same concept."
    )


# ============================================================================
# 11. EDGE CASES AND FAILURE MODES
# ============================================================================

def demonstrate_edge_cases() -> None:
    section("12. Edge Cases and Failure Modes")

    subsection("No matching route")
    routes = [
        Route(
            IPv4Network("192.168.1.0/24"),
            None,
            "eth0",
        )
    ]
    destination = "10.0.0.1"
    result = choose_route(routes, destination)
    print(f"Destination {destination}: {result}")

    subsection("Overlapping routes")
    overlapping = [
        Route(
            IPv4Network("10.0.0.0/8"),
            IPv4Address("192.0.2.1"),
            "eth0",
            100,
        ),
        Route(
            IPv4Network("10.10.0.0/16"),
            IPv4Address("192.0.2.2"),
            "eth1",
            100,
        ),
    ]
    result = choose_route(overlapping, "10.10.5.20")
    print(
        f"10.10.5.20 selects {result.network} through {result.next_hop}"
    )

    subsection("Equal prefix, different metric")
    equal_prefix = [
        Route(
            IPv4Network("10.20.0.0/16"),
            IPv4Address("192.0.2.10"),
            "eth0",
            50,
        ),
        Route(
            IPv4Network("10.20.0.0/16"),
            IPv4Address("192.0.2.11"),
            "eth1",
            100,
        ),
    ]
    result = choose_route(equal_prefix, "10.20.1.1")
    print(
        f"Equal-prefix routes select lower metric: "
        f"{result.next_hop} metric={result.metric}"
    )

    subsection("TTL expiration")
    router = Router("Failure-Router")
    router.add_route(
        "0.0.0.0/0",
        "192.0.2.1",
        "wan",
    )
    packet = Packet(
        IPv4Address("192.168.1.10"),
        IPv4Address("8.8.8.8"),
        50000,
        443,
        "TCP",
        ttl=1,
    )
    try:
        router.forward(packet)
    except RuntimeError as exc:
        print(f"Expected failure: {exc}")

    subsection("NAT state missing")
    nat = PortAddressTranslation("203.0.113.50")
    response = Packet(
        IPv4Address("198.51.100.10"),
        IPv4Address("203.0.113.50"),
        443,
        41000,
        "TCP",
    )
    try:
        nat.translate_inbound(response)
    except RuntimeError as exc:
        print(f"Expected failure: {exc}")

    subsection("Important operational failures")
    failures = [
        "Incorrect subnet mask/prefix",
        "Wrong default gateway",
        "Missing route",
        "Incorrect next hop",
        "Routing loop",
        "Expired TTL",
        "NAT state timeout",
        "NAT port exhaustion",
        "Firewall or ACL filtering",
        "Asymmetric routing",
        "MTU/fragmentation problems",
        "DNS failure mistaken for routing failure",
    ]
    for failure in failures:
        print(f"- {failure}")


# ============================================================================
# 12. ROUTING LOOP DETECTION
# ============================================================================

@dataclass
class ForwardingResult:
    delivered: bool
    hops: list[str]
    reason: str


def simulate_forwarding_chain(
    packet: Packet,
    routers: list[Router],
    destination_network: IPv4Network,
) -> ForwardingResult:
    hops = []

    for router in routers:
        hops.append(router.name)

        try:
            route = router.forward(packet)
        except RuntimeError as exc:
            return ForwardingResult(False, hops, str(exc))

        if packet.destination_ip in destination_network:
            return ForwardingResult(
                True,
                hops,
                f"destination network reachable via {route.interface}",
            )

    return ForwardingResult(
        False,
        hops,
        "maximum simulated forwarding depth reached",
    )


def demo_forwarding_failure() -> None:
    section("13. Routing Failure Analysis")

    router_a = Router("R-A")
    router_a.add_route(
        "0.0.0.0/0",
        "192.0.2.2",
        "wan",
    )

    router_b = Router("R-B")
    router_b.add_route(
        "0.0.0.0/0",
        "192.0.2.1",
        "wan",
    )

    packet = Packet(
        IPv4Address("10.0.0.10"),
        IPv4Address("8.8.8.8"),
        50000,
        443,
        "TCP",
        ttl=5,
    )

    result = simulate_forwarding_chain(
        packet,
        [router_a, router_b, router_a, router_b, router_a, router_b],
        IPv4Network("8.8.8.0/24"),
    )

    print("Path:", " -> ".join(result.hops))
    print("Delivered:", result.delivered)
    print("Reason:", result.reason)

    print(
        "\nA real routing loop can repeatedly send packets between routers "
        "until TTL expires. This is one reason TTL exists."
    )


# ============================================================================
# 13. PERFORMANCE AND DESIGN CONSIDERATIONS
# ============================================================================

def performance_discussion() -> None:
    section("14. Performance and Design Considerations")

    considerations = {
        "Routing lookup": (
            "Routers need efficient longest-prefix matching. Hardware "
            "forwarding tables, TCAM, trie structures, and optimized software "
            "lookups can reduce per-packet lookup cost."
        ),
        "NAT state": (
            "PAT requires state lookup for each translated flow. Large NAT "
            "devices therefore need efficient state tables, timers, port "
            "allocation, and resource management."
        ),
        "Routing convergence": (
            "Dynamic routing systems must exchange and process route changes. "
            "Faster convergence can improve availability but may increase "
            "control-plane complexity."
        ),
        "MTU": (
            "Different links can have different maximum transmission units. "
            "Packets that exceed a path's usable MTU may be fragmented or "
            "require path-MTU mechanisms."
        ),
        "Asymmetric paths": (
            "The outbound and return paths do not necessarily have to be "
            "identical. Stateful firewalls and NAT devices therefore need "
            "careful placement and state visibility."
        ),
    }

    for name, description in considerations.items():
        print(f"\n{name}:")
        print(f"  {description}")


# ============================================================================
# 14. SECURITY CONSIDERATIONS
# ============================================================================

def security_discussion() -> None:
    section("15. Security Considerations")

    points = [
        (
            "NAT is not a complete security boundary",
            "Address translation can reduce unsolicited inbound reachability "
            "in common configurations, but firewall policy is the actual "
            "mechanism for explicitly controlling traffic."
        ),
        (
            "Private addresses are not automatically trusted",
            "An internal RFC 1918 address does not prove that traffic is safe "
            "or that the sender is authorized."
        ),
        (
            "Route manipulation",
            "Unauthorized route changes can redirect, blackhole, or intercept "
            "traffic. Routing infrastructure therefore requires access control "
            "and authenticated management."
        ),
        (
            "Traceroute exposure",
            "Traceroute can reveal network topology when intermediate devices "
            "respond to probes. Network policy can limit such exposure."
        ),
        (
            "NAT state exhaustion",
            "An attacker or accidental workload can consume translation "
            "entries or ephemeral ports, preventing new connections."
        ),
        (
            "Management-plane security",
            "Routing configuration, router management interfaces, and "
            "monitoring systems should be protected separately from ordinary "
            "forwarding traffic."
        ),
    ]

    for title, explanation in points:
        print(f"\n{title}:")
        print(f"  {explanation}")


# ============================================================================
# 15. DIAGNOSTIC WORKFLOW
# ============================================================================

def diagnostic_workflow() -> None:
    section("16. Practical Routing and NAT Troubleshooting")

    steps = [
        "1. Confirm the interface is up.",
        "2. Confirm the host has the expected IP address and prefix.",
        "3. Confirm the destination is correctly identified.",
        "4. Determine whether the destination is local or requires a gateway.",
        "5. Inspect the host routing table.",
        "6. Verify the default gateway and next hop.",
        "7. Test reachability of the gateway.",
        "8. Inspect routing tables on relevant routers.",
        "9. Check NAT/SNAT/PAT state where translation is expected.",
        "10. Check firewall and ACL policy.",
        "11. Use traceroute/tracert to observe the path.",
        "12. Check DNS separately so name-resolution failures are not mistaken "
        "for routing failures.",
        "13. Check return routing because successful outbound routing does not "
        "guarantee a valid return path.",
        "14. Check MTU and packet-size behavior when small packets work but "
        "larger traffic fails.",
    ]

    for step in steps:
        print(step)

    print(
        "\nUseful Linux commands:\n"
        "  ip addr\n"
        "  ip route\n"
        "  ip route get 8.8.8.8\n"
        "  ping 8.8.8.8\n"
        "  traceroute 8.8.8.8\n"
        "\n"
        "Useful Windows commands:\n"
        "  ipconfig\n"
        "  route print\n"
        "  tracert 8.8.8.8\n"
        "  ping 8.8.8.8"
    )


# ============================================================================
# 16. ROUTE SELECTION TESTS
# ============================================================================

def run_self_tests() -> None:
    section("17. Built-In Self Tests")

    routes = [
        Route(
            IPv4Network("0.0.0.0/0"),
            IPv4Address("192.168.1.1"),
            "default",
            100,
        ),
        Route(
            IPv4Network("10.0.0.0/8"),
            IPv4Address("192.168.1.2"),
            "private",
            100,
        ),
        Route(
            IPv4Network("10.1.0.0/16"),
            IPv4Address("192.168.1.3"),
            "regional",
            100,
        ),
        Route(
            IPv4Network("10.1.2.0/24"),
            IPv4Address("192.168.1.4"),
            "local",
            100,
        ),
    ]

    assert choose_route(routes, "10.1.2.99").network == IPv4Network(
        "10.1.2.0/24"
    )
    assert choose_route(routes, "10.1.99.99").network == IPv4Network(
        "10.1.0.0/16"
    )
    assert choose_route(routes, "10.99.99.99").network == IPv4Network(
        "10.0.0.0/8"
    )
    assert choose_route(routes, "8.8.8.8").network == IPv4Network(
        "0.0.0.0/0"
    )

    nat = PortAddressTranslation("203.0.113.100")

    first = Packet(
        IPv4Address("192.168.1.10"),
        IPv4Address("198.51.100.20"),
        50000,
        443,
        "TCP",
    )
    second = Packet(
        IPv4Address("192.168.1.11"),
        IPv4Address("198.51.100.20"),
        50000,
        443,
        "TCP",
    )

    first_translated = nat.translate_outbound(first)
    second_translated = nat.translate_outbound(second)

    assert first_translated.source_ip == IPv4Address("203.0.113.100")
    assert second_translated.source_ip == IPv4Address("203.0.113.100")
    assert first_translated.source_port != second_translated.source_port

    response = Packet(
        IPv4Address("198.51.100.20"),
        first_translated.source_ip,
        443,
        first_translated.source_port,
        "TCP",
    )
    restored = nat.translate_inbound(response)

    assert restored.destination_ip == first.source_ip
    assert restored.destination_port == first.source_port

    print("All route-selection and NAT tests passed.")


# ============================================================================
# 17. MINI QUIZ
# ============================================================================

def knowledge_check() -> None:
    section("18. Knowledge Check")

    questions = [
        (
            "1. Which route normally wins: 10.0.0.0/8 or 10.10.0.0/16?",
            "10.10.0.0/16 because it has the longer prefix."
        ),
        (
            "2. What does a default route represent?",
            "A fallback route used when no more-specific route matches."
        ),
        (
            "3. Why does PAT use ports?",
            "Ports allow multiple simultaneous flows to share a public IP."
        ),
        (
            "4. What does TTL help prevent?",
            "Packets circulating indefinitely in routing loops."
        ),
        (
            "5. Does NAT replace routing?",
            "No. Translation and routing are separate functions that may "
            "operate on the same gateway device."
        ),
        (
            "6. What can traceroute reveal?",
            "Observed intermediate hops and approximate response latency, "
            "subject to filtering and path behavior."
        ),
    ]

    for question, answer in questions:
        print(f"\n{question}\nAnswer: {answer}")


# ============================================================================
# 18. MAIN PROGRAM
# ============================================================================

def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Comprehensive educational demonstration of IPv4 routing, "
            "gateways, routers, NAT/PAT, and traceroute concepts."
        )
    )
    parser.add_argument(
        "--real-route",
        action="store_true",
        help="Read and display the host's current routing table.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run built-in assertions.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run the core simulated demonstrations only.",
    )
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    random.seed(42)

    demo_addressing()
    demo_longest_prefix()
    demo_router()
    demo_gateway()
    demo_nat()
    explain_nat_types()
    demo_end_to_end()
    demo_traceroute()

    if not args.quick:
        explain_routing_protocols()
        demonstrate_edge_cases()
        demo_forwarding_failure()
        performance_discussion()
        security_discussion()
        diagnostic_workflow()
        knowledge_check()

    if args.real_route:
        show_real_routing_table()
        show_interface_addresses()

    if args.self_test:
        run_self_tests()

    section("19. Key Operational Model")

    print(
        "Host routing decision:\n"
        "  1. Is the destination directly reachable?\n"
        "  2. If not, which route has the longest matching prefix?\n"
        "  3. What next hop and interface does that route specify?\n\n"
        "Router forwarding decision:\n"
        "  1. Receive packet.\n"
        "  2. Decrement TTL.\n"
        "  3. Perform longest-prefix route lookup.\n"
        "  4. Apply forwarding/NAT policy where configured.\n"
        "  5. Send toward the selected next hop/interface.\n\n"
        "Private-to-public model:\n"
        "  private host -> gateway -> NAT/PAT -> public network -> server\n"
        "  server -> public NAT endpoint -> reverse NAT -> private host\n\n"
        "Diagnostic model:\n"
        "  address -> subnet -> gateway -> route -> next hop -> NAT -> ACL -> "
        "return route"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
