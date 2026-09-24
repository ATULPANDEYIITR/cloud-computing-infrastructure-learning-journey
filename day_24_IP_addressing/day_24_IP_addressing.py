"""
IP Addressing: IPv4, IPv6, Public IP, Private IP, Reserved Addresses, and IP Allocation

A self-contained study and demonstration program progressing from beginner concepts
to practical and advanced IP addressing operations.

No external packages are required.
"""

from __future__ import annotations

import ipaddress
import itertools
import math
import random
from dataclasses import dataclass
from typing import Iterable


# =============================================================================
# SECTION 1: FUNDAMENTALS
# =============================================================================

def print_title(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def print_subtitle(title: str) -> None:
    print("\n" + "-" * 60)
    print(title)
    print("-" * 60)


def explain_ip_basics() -> None:
    print_title("1. IP ADDRESSING FUNDAMENTALS")

    print("""
An IP address identifies a network interface at the Internet Protocol layer.

Two major versions are in practical use:

IPv4
    - 32 bits.
    - Usually written as four decimal octets.
    - Example: 192.168.1.10
    - Address space: 2^32 addresses.

IPv6
    - 128 bits.
    - Usually written as eight hexadecimal groups.
    - Example: 2001:db8:1234::10
    - Address space: 2^128 addresses.

An address is not just a number. Its meaning depends on the network prefix,
scope, allocation rules, and context in which it is used.
""")

    ipv4_count = 2**32
    ipv6_count = 2**128

    print(f"Total IPv4 address values: {ipv4_count:,}")
    print(f"Total IPv6 address values: {ipv6_count:,}")
    print(f"IPv6-to-IPv4 address-space ratio: {ipv6_count / ipv4_count:.3e}")


# =============================================================================
# SECTION 2: BINARY REPRESENTATION
# =============================================================================

def ipv4_to_binary(address: str) -> str:
    """Convert dotted-decimal IPv4 into a 32-bit binary string."""
    ip = ipaddress.IPv4Address(address)
    return format(int(ip), "032b")


def binary_to_ipv4(binary: str) -> str:
    """Convert exactly 32 binary bits into dotted-decimal IPv4."""
    if len(binary) != 32 or any(bit not in "01" for bit in binary):
        raise ValueError("IPv4 binary representation must contain exactly 32 bits.")
    return str(ipaddress.IPv4Address(int(binary, 2)))


def demonstrate_binary() -> None:
    print_title("2. IPv4 BINARY REPRESENTATION")

    address = "192.168.10.25"
    binary = ipv4_to_binary(address)

    print(f"IPv4 address: {address}")
    print(f"Binary:       {binary}")
    print(f"Round trip:   {binary_to_ipv4(binary)}")

    octets = address.split(".")
    print("\nOctet-by-octet:")
    for octet in octets:
        print(f"{octet:>3} -> {int(octet):08b}")


# =============================================================================
# SECTION 3: NETWORK PREFIX AND SUBNET MASK
# =============================================================================

def subnet_details(cidr: str) -> dict[str, object]:
    """
    Return important properties of an IPv4 or IPv6 network.

    strict=False allows an address such as 192.168.1.17/24 to be interpreted
    as the network 192.168.1.0/24 instead of requiring host bits to be zero.
    """
    interface = ipaddress.ip_interface(cidr)
    network = interface.network

    return {
        "address": interface.ip,
        "prefix_length": network.prefixlen,
        "network": network.network_address,
        "broadcast": getattr(network, "broadcast_address", None),
        "netmask": network.netmask,
        "hostmask": network.hostmask,
        "num_addresses": network.num_addresses,
        "version": interface.version,
        "is_private": interface.ip.is_private,
        "is_global": interface.ip.is_global,
        "is_loopback": interface.ip.is_loopback,
        "is_link_local": interface.ip.is_link_local,
        "is_multicast": interface.ip.is_multicast,
    }


def demonstrate_subnetting() -> None:
    print_title("3. SUBNETTING AND CIDR")

    examples = [
        "192.168.1.25/24",
        "10.20.30.40/16",
        "172.16.5.9/20",
        "2001:db8:1234:5678::25/64",
    ]

    for cidr in examples:
        details = subnet_details(cidr)
        print_subtitle(cidr)
        for key, value in details.items():
            print(f"{key:>15}: {value}")

    print("""
CIDR notation combines an IP address with a prefix length.

For example:

    192.168.1.25/24

The /24 means that the first 24 bits identify the network and the remaining
8 bits are available for host addressing within that IPv4 subnet.

IPv4:
    host bits = 32 - prefix length
    address count = 2^(host bits)

IPv6:
    host bits = 128 - prefix length
    address count = 2^(host bits)

For ordinary IPv4 subnets, the first and last addresses traditionally have
special roles as the network and broadcast addresses. IPv6 does not use
broadcast addressing; multicast is used for one-to-many communication.
""")


# =============================================================================
# SECTION 4: IPv4 SPECIAL ADDRESS CATEGORIES
# =============================================================================

def classify_ip(address: str) -> dict[str, object]:
    ip = ipaddress.ip_address(address)

    return {
        "address": str(ip),
        "version": ip.version,
        "private": ip.is_private,
        "global": ip.is_global,
        "loopback": ip.is_loopback,
        "link_local": ip.is_link_local,
        "multicast": ip.is_multicast,
        "unspecified": ip.is_unspecified,
        "reserved": ip.is_reserved,
    }


def demonstrate_classification() -> None:
    print_title("4. IP ADDRESS CLASSIFICATION")

    addresses = [
        "0.0.0.0",
        "8.8.8.8",
        "10.0.0.1",
        "100.64.0.1",
        "127.0.0.1",
        "169.254.10.20",
        "172.16.10.5",
        "192.168.1.20",
        "192.0.2.10",
        "198.51.100.20",
        "203.0.113.30",
        "224.0.0.1",
        "255.255.255.255",
        "::",
        "::1",
        "fe80::1",
        "fc00::1",
        "2001:db8::1",
        "ff02::1",
    ]

    for address in addresses:
        try:
            classification = classify_ip(address)
        except ValueError as exc:
            print(f"{address}: invalid ({exc})")
            continue

        print(f"\n{address}")
        for key, value in classification.items():
            if key != "address":
                print(f"  {key:>12}: {value}")


# =============================================================================
# SECTION 5: PRIVATE ADDRESS SPACE
# =============================================================================

PRIVATE_IPV4_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]


def is_rfc1918_private_ipv4(address: str) -> bool:
    ip = ipaddress.IPv4Address(address)
    return any(ip in network for network in PRIVATE_IPV4_NETWORKS)


def demonstrate_private_ranges() -> None:
    print_title("5. PRIVATE IPv4 ADDRESSING")

    print("RFC 1918 private IPv4 ranges:")
    for network in PRIVATE_IPV4_NETWORKS:
        print(f"  {network}")

    test_addresses = [
        "10.25.30.40",
        "172.15.1.1",
        "172.16.1.1",
        "172.31.255.254",
        "172.32.1.1",
        "192.168.100.50",
        "192.169.1.1",
    ]

    for address in test_addresses:
        print(
            f"{address:>16} -> "
            f"{'RFC 1918 private' if is_rfc1918_private_ipv4(address) else 'not RFC 1918 private'}"
        )

    print("""
Private IPv4 addresses are intended for internal networks and are not
globally routed as ordinary public Internet destinations.

A private address can be reused independently by different organizations.

NAT is commonly used when hosts with private IPv4 addresses communicate
through a gateway that represents them using a public IPv4 address.
""")


# =============================================================================
# SECTION 6: PUBLIC IP AND NAT CONCEPTS
# =============================================================================

@dataclass
class NatTranslation:
    private_source: str
    private_port: int
    public_source: str
    public_port: int
    destination: str
    destination_port: int


class SimpleNatTable:
    """Educational model of a stateful source NAT/PAT table."""

    def __init__(self, public_ip: str, starting_port: int = 40000) -> None:
        self.public_ip = ipaddress.IPv4Address(public_ip)
        self.next_port = starting_port
        self.table: list[NatTranslation] = []

    def translate(
        self,
        private_source: str,
        private_port: int,
        destination: str,
        destination_port: int,
    ) -> NatTranslation:
        if not is_rfc1918_private_ipv4(private_source):
            raise ValueError("This educational NAT model expects an RFC 1918 source address.")

        public_port = self.next_port
        self.next_port += 1

        translation = NatTranslation(
            private_source=private_source,
            private_port=private_port,
            public_source=str(self.public_ip),
            public_port=public_port,
            destination=destination,
            destination_port=destination_port,
        )

        self.table.append(translation)
        return translation

    def display(self) -> None:
        for entry in self.table:
            print(
                f"{entry.private_source}:{entry.private_port}"
                f" -> {entry.public_source}:{entry.public_port}"
                f" -> {entry.destination}:{entry.destination_port}"
            )


def demonstrate_nat() -> None:
    print_title("6. PUBLIC IP, PRIVATE IP, AND NAT")

    nat = SimpleNatTable("203.0.113.10")

    connections = [
        ("192.168.1.10", 51500, "93.184.216.34", 443),
        ("192.168.1.11", 51501, "142.250.72.14", 443),
        ("10.0.0.25", 51502, "198.51.100.50", 80),
    ]

    for connection in connections:
        nat.translate(*connection)

    print("Educational NAT/PAT translation table:")
    nat.display()

    print("""
NAT is not the same thing as IP addressing.

NAT changes packet address information at a network boundary. Port Address
Translation (PAT), often called NAT overload, can let many internal flows
share one public IPv4 address by distinguishing connections with transport
ports.

NAT can complicate:
    - inbound connectivity
    - peer-to-peer applications
    - protocol inspection
    - logging
    - troubleshooting
    - end-to-end communication

NAT should not be treated as a substitute for a firewall. Security policy
and stateful filtering are separate functions.
""")


# =============================================================================
# SECTION 7: SPECIAL IPv4 RANGES
# =============================================================================

SPECIAL_RANGES = {
    "unspecified": ipaddress.ip_network("0.0.0.0/8"),
    "private_10": ipaddress.ip_network("10.0.0.0/8"),
    "shared_address_space": ipaddress.ip_network("100.64.0.0/10"),
    "loopback": ipaddress.ip_network("127.0.0.0/8"),
    "link_local": ipaddress.ip_network("169.254.0.0/16"),
    "documentation_1": ipaddress.ip_network("192.0.2.0/24"),
    "documentation_2": ipaddress.ip_network("198.51.100.0/24"),
    "documentation_3": ipaddress.ip_network("203.0.113.0/24"),
    "multicast": ipaddress.ip_network("224.0.0.0/4"),
}


def ranges_containing(address: str) -> list[str]:
    ip = ipaddress.ip_address(address)
    return [name for name, network in SPECIAL_RANGES.items() if ip.version == network.version and ip in network]


def demonstrate_special_ranges() -> None:
    print_title("7. IMPORTANT IPv4 SPECIAL-PURPOSE RANGES")

    for name, network in SPECIAL_RANGES.items():
        print(f"{name:>22}: {network}")

    print("\nClassification examples:")
    for address in [
        "0.0.0.0",
        "100.64.20.1",
        "127.0.0.1",
        "169.254.1.1",
        "192.0.2.1",
        "198.51.100.1",
        "203.0.113.1",
        "224.0.0.1",
    ]:
        print(f"{address:>15}: {ranges_containing(address)}")


# =============================================================================
# SECTION 8: IPv6 FUNDAMENTALS
# =============================================================================

def demonstrate_ipv6() -> None:
    print_title("8. IPv6 ADDRESSING")

    addresses = [
        "2001:0db8:0000:0000:0000:ff00:0042:8329",
        "2001:db8::1",
        "::1",
        "::",
        "fe80::abcd",
        "fc00::1",
        "fd12:3456:789a::1",
        "ff02::1",
        "::ffff:192.0.2.128",
    ]

    for text_address in addresses:
        ip = ipaddress.IPv6Address(text_address)

        print(f"\nOriginal:     {text_address}")
        print(f"Compressed:   {ip.compressed}")
        print(f"Exploded:     {ip.exploded}")
        print(f"Integer:      {int(ip)}")
        print(f"Private:      {ip.is_private}")
        print(f"Global:       {ip.is_global}")
        print(f"Loopback:     {ip.is_loopback}")
        print(f"Link-local:   {ip.is_link_local}")
        print(f"Multicast:    {ip.is_multicast}")
        print(f"IPv4-mapped:  {ip.ipv4_mapped}")

    print("""
IPv6 notation permits compression.

The sequence of one or more consecutive all-zero 16-bit groups can be
represented by :: once in an address.

For example:

    2001:0db8:0000:0000:0000:0000:0000:0001
    becomes
    2001:db8::1

The :: notation cannot be used more than once in a single textual IPv6
address because otherwise the number of omitted groups would be ambiguous.
""")


# =============================================================================
# SECTION 9: IPv6 ADDRESS TYPES
# =============================================================================

def demonstrate_ipv6_scopes() -> None:
    print_title("9. IPv6 ADDRESS TYPES AND SCOPES")

    examples = [
        ("::1", "loopback"),
        ("::", "unspecified"),
        ("fe80::1", "link-local"),
        ("fc00::1", "unique-local style address"),
        ("2001:db8::1", "documentation prefix"),
        ("ff02::1", "link-local multicast"),
        ("ff05::2", "site-local scope multicast example"),
    ]

    for address, description in examples:
        ip = ipaddress.IPv6Address(address)
        print(f"{address:>25} | {description:35} | compressed={ip.compressed}")

    print("""
Common IPv6 categories include:

    ::1
        Loopback.

    ::
        Unspecified address.

    fe80::/10
        Link-local unicast addresses. These are used for communication on
        a local link and are not globally routed.

    fc00::/7
        Unique Local Address (ULA) space. fd00::/8 is commonly used for
        locally assigned ULA networks.

    ff00::/8
        Multicast.

    2000::/3
        Global unicast address space used for Internet-scale unicast
        addressing, subject to allocation and routing policy.

    2001:db8::/32
        Documentation prefix reserved for examples and documentation.

IPv6 has no broadcast address. Multicast provides several functions that
broadcast provided in IPv4.
""")


# =============================================================================
# SECTION 10: SUBNET CALCULATIONS
# =============================================================================

def ipv4_subnet_math(prefix_length: int) -> dict[str, int | float]:
    if not 0 <= prefix_length <= 32:
        raise ValueError("IPv4 prefix length must be between 0 and 32.")

    host_bits = 32 - prefix_length
    total = 2**host_bits

    if prefix_length <= 30:
        usable = max(total - 2, 0)
    else:
        usable = total

    return {
        "prefix_length": prefix_length,
        "host_bits": host_bits,
        "total_addresses": total,
        "traditional_usable_host_addresses": usable,
    }


def ipv6_subnet_math(prefix_length: int) -> dict[str, int]:
    if not 0 <= prefix_length <= 128:
        raise ValueError("IPv6 prefix length must be between 0 and 128.")

    host_bits = 128 - prefix_length
    return {
        "prefix_length": prefix_length,
        "host_bits": host_bits,
        "total_addresses": 2**host_bits,
    }


def demonstrate_subnet_math() -> None:
    print_title("10. SUBNET CAPACITY CALCULATIONS")

    for prefix in [8, 16, 20, 24, 25, 26, 27, 28, 29, 30, 31, 32]:
        result = ipv4_subnet_math(prefix)
        print(
            f"/{prefix:2} -> "
            f"host bits={result['host_bits']:2}, "
            f"total={result['total_addresses']:>12,}, "
            f"traditional usable={result['traditional_usable_host_addresses']:>12,}"
        )

    print("\nIPv6 examples:")
    for prefix in [32, 48, 56, 64, 96, 128]:
        result = ipv6_subnet_math(prefix)
        print(
            f"/{prefix:3} -> host bits={result['host_bits']:3}, "
            f"addresses={result['total_addresses']:,}"
        )

    print("""
The traditional IPv4 usable-host formula is not universally applicable.

For example:
    /31
        Commonly used for point-to-point links under RFC 3021.

    /32
        Represents one IPv4 address.

IPv6 subnet planning also follows different conventions. A /64 is a common
subnet size for IPv6 end-user networks, and many IPv6 mechanisms assume a
64-bit interface identifier boundary.
""")


# =============================================================================
# SECTION 11: VLSM
# =============================================================================

@dataclass
class VlsmRequirement:
    name: str
    required_hosts: int


def minimum_ipv4_prefix_for_hosts(required_hosts: int) -> int:
    if required_hosts < 1:
        raise ValueError("Host requirement must be positive.")

    host_bits = 0
    while 2**host_bits - 2 < required_hosts:
        host_bits += 1

    return 32 - host_bits


def allocate_vlsm(base_network: str, requirements: Iterable[VlsmRequirement]) -> list[tuple[str, ipaddress.IPv4Network]]:
    """
    Allocate variable-length subnets from a base network.

    Largest requirements are allocated first to reduce fragmentation.
    """
    base = ipaddress.ip_network(base_network, strict=True)

    if base.version != 4:
        raise ValueError("This VLSM allocator supports IPv4 only.")

    ordered = sorted(requirements, key=lambda item: item.required_hosts, reverse=True)

    allocations: list[tuple[str, ipaddress.IPv4Network]] = []
    cursor = int(base.network_address)
    base_end = int(base.broadcast_address)

    for requirement in ordered:
        prefix = minimum_ipv4_prefix_for_hosts(requirement.required_hosts)
        block_size = 2 ** (32 - prefix)

        # Align the cursor to the subnet boundary.
        aligned_cursor = ((cursor + block_size - 1) // block_size) * block_size
        candidate = ipaddress.IPv4Network((aligned_cursor, prefix))

        if int(candidate.broadcast_address) > base_end:
            raise ValueError(
                f"Insufficient address space for {requirement.name} "
                f"requiring {requirement.required_hosts} hosts."
            )

        allocations.append((requirement.name, candidate))
        cursor = int(candidate.broadcast_address) + 1

    return allocations


def demonstrate_vlsm() -> None:
    print_title("11. VARIABLE-LENGTH SUBNET MASKING (VLSM)")

    requirements = [
        VlsmRequirement("Engineering", 100),
        VlsmRequirement("Finance", 30),
        VlsmRequirement("Operations", 50),
        VlsmRequirement("Management", 10),
        VlsmRequirement("Point-to-point", 2),
    ]

    base = "192.168.50.0/24"

    print(f"Base network: {base}")
    print("Requirements:")

    for requirement in requirements:
        print(f"  {requirement.name:15} -> {requirement.required_hosts} hosts")

    print("\nAllocated subnets:")
    try:
        for name, network in allocate_vlsm(base, requirements):
            print(
                f"  {name:15} -> {network} "
                f"({network.num_addresses} addresses)"
            )
    except ValueError as exc:
        print(f"Allocation failed: {exc}")

    print("""
VLSM allows different subnet sizes inside a larger address block.

The important planning principle is to allocate larger blocks first. If small
blocks consume addresses at arbitrary positions before a large requirement is
processed, fragmentation can prevent an otherwise sufficient address pool
from being allocated efficiently.
""")


# =============================================================================
# SECTION 12: IP ALLOCATION
# =============================================================================

@dataclass
class AllocationRecord:
    organization: str
    network: ipaddress._BaseNetwork
    purpose: str


class IpamPool:
    """Small educational IP Address Management pool."""

    def __init__(self, network: str) -> None:
        self.network = ipaddress.ip_network(network)
        self.allocations: list[AllocationRecord] = []

    def overlaps_existing(self, candidate: ipaddress._BaseNetwork) -> bool:
        return any(candidate.overlaps(record.network) for record in self.allocations)

    def allocate(self, organization: str, prefix_length: int, purpose: str) -> ipaddress._BaseNetwork:
        if prefix_length < self.network.prefixlen:
            raise ValueError("Requested subnet is larger than the available pool.")

        if prefix_length > self.network.max_prefixlen:
            raise ValueError("Invalid prefix length.")

        for candidate in self.network.subnets(new_prefix=prefix_length):
            if not self.overlaps_existing(candidate):
                self.allocations.append(
                    AllocationRecord(organization, candidate, purpose)
                )
                return candidate

        raise RuntimeError("No non-overlapping subnet is available.")

    def release(self, network: str) -> None:
        target = ipaddress.ip_network(network)
        before = len(self.allocations)
        self.allocations = [
            record for record in self.allocations if record.network != target
        ]

        if len(self.allocations) == before:
            raise KeyError(f"Allocation {target} was not found.")

    def display(self) -> None:
        for record in self.allocations:
            print(
                f"{record.organization:15} "
                f"{str(record.network):18} "
                f"{record.purpose}"
            )


def demonstrate_ipam() -> None:
    print_title("12. IP ADDRESS MANAGEMENT (IPAM)")

    pool = IpamPool("10.50.0.0/16")

    requests = [
        ("Engineering", 24, "application servers"),
        ("Finance", 26, "workstations"),
        ("Operations", 25, "internal services"),
        ("Security", 27, "security infrastructure"),
    ]

    for organization, prefix, purpose in requests:
        allocated = pool.allocate(organization, prefix, purpose)
        print(f"Allocated {allocated} to {organization}")

    print("\nCurrent allocation table:")
    pool.display()

    print("\nReleasing Finance allocation...")
    finance_network = next(
        record.network
        for record in pool.allocations
        if record.organization == "Finance"
    )
    pool.release(str(finance_network))
    pool.display()

    print("""
Real IPAM systems usually track more than CIDR blocks.

Typical metadata includes:
    - owner
    - business unit
    - environment
    - location
    - VLAN
    - DNS zone
    - gateway
    - DHCP scope
    - allocation state
    - reservation state
    - creation date
    - expiration or review date
    - routing domain

A disciplined IPAM process reduces overlapping subnets, undocumented ranges,
and troubleshooting ambiguity.
""")


# =============================================================================
# SECTION 13: DHCP CONCEPT
# =============================================================================

class DhcpPool:
    """Simplified DHCP-style address allocator for an IPv4 subnet."""

    def __init__(self, network: str, excluded: Iterable[str] = ()) -> None:
        self.network = ipaddress.ip_network(network, strict=True)
        self.excluded = {ipaddress.ip_address(address) for address in excluded}
        self.leases: dict[str, ipaddress.IPv4Address] = {}

    def offer(self, client_identifier: str) -> ipaddress.IPv4Address:
        if client_identifier in self.leases:
            return self.leases[client_identifier]

        for host in self.network.hosts():
            if host in self.excluded or host in self.leases.values():
                continue

            self.leases[client_identifier] = host
            return host

        raise RuntimeError("DHCP pool has no available addresses.")

    def release(self, client_identifier: str) -> None:
        self.leases.pop(client_identifier, None)


def demonstrate_dhcp() -> None:
    print_title("13. DHCP-STYLE ADDRESS ALLOCATION")

    pool = DhcpPool(
        "192.168.60.0/24",
        excluded=["192.168.60.1", "192.168.60.2", "192.168.60.10"],
    )

    clients = ["laptop-A", "laptop-B", "printer-A", "phone-A"]

    for client in clients:
        print(f"{client:12} -> {pool.offer(client)}")

    print("\nRequesting again for laptop-A:")
    print(f"laptop-A -> {pool.offer('laptop-A')}")

    print("\nReleasing phone-A and allocating to tablet-A:")
    pool.release("phone-A")
    print(f"tablet-A -> {pool.offer('tablet-A')}")

    print("""
DHCP commonly supplies configuration such as:

    - IP address
    - subnet mask
    - default gateway
    - DNS servers
    - lease duration

DHCP is an allocation mechanism. It is distinct from the IP address space
itself and from routing.
""")


# =============================================================================
# SECTION 14: ROUTING PREFIX MATCHING
# =============================================================================

@dataclass
class Route:
    network: ipaddress._BaseNetwork
    next_hop: str


class RoutingTable:
    """Educational longest-prefix-match routing table."""

    def __init__(self) -> None:
        self.routes: list[Route] = []

    def add_route(self, network: str, next_hop: str) -> None:
        self.routes.append(
            Route(ipaddress.ip_network(network), next_hop)
        )

    def lookup(self, destination: str) -> Route | None:
        ip = ipaddress.ip_address(destination)
        matches = [route for route in self.routes if ip in route.network]

        if not matches:
            return None

        # Longest-prefix match selects the most specific matching route.
        return max(matches, key=lambda route: route.network.prefixlen)


def demonstrate_routing() -> None:
    print_title("14. ROUTING AND LONGEST-PREFIX MATCH")

    table = RoutingTable()

    table.add_route("0.0.0.0/0", "Internet Gateway")
    table.add_route("10.0.0.0/8", "Internal Router A")
    table.add_route("10.20.0.0/16", "Internal Router B")
    table.add_route("10.20.30.0/24", "Internal Router C")
    table.add_route("10.20.30.128/25", "Internal Router D")

    destinations = [
        "8.8.8.8",
        "10.5.5.5",
        "10.20.5.5",
        "10.20.30.50",
        "10.20.30.200",
    ]

    for destination in destinations:
        route = table.lookup(destination)

        if route:
            print(
                f"{destination:15} -> "
                f"{str(route.network):18} -> {route.next_hop}"
            )
        else:
            print(f"{destination:15} -> no route")

    print("""
Routing decisions are not normally made simply by asking whether an address
is "public" or "private."

Routers compare the destination address against routing prefixes.

When multiple routes match, longest-prefix match generally chooses the route
with the greatest prefix length, meaning the most specific matching route.
""")


# =============================================================================
# SECTION 15: VALIDATION AND ERROR HANDLING
# =============================================================================

def validate_ip_address(value: str) -> tuple[bool, str]:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False, "Invalid IP address syntax."

    if ip.version == 4:
        return True, "Valid IPv4 address."
    return True, "Valid IPv6 address."


def validate_network(value: str) -> tuple[bool, str]:
    try:
        network = ipaddress.ip_network(value, strict=True)
    except ValueError as exc:
        return False, f"Invalid network: {exc}"

    return True, f"Valid IPv{network.version} network."


def demonstrate_validation() -> None:
    print_title("15. VALIDATION AND EDGE CASES")

    addresses = [
        "192.168.1.1",
        "192.168.1.999",
        "2001:db8::1",
        "2001:db8:::1",
        "127.0.0.1",
        "",
        "localhost",
    ]

    for value in addresses:
        valid, message = validate_ip_address(value)
        print(f"{value!r:22} -> {valid:5} -> {message}")

    print("\nNetwork validation:")
    networks = [
        "192.168.1.0/24",
        "192.168.1.10/24",
        "2001:db8::/32",
        "10.0.0.0/33",
    ]

    for value in networks:
        valid, message = validate_network(value)
        print(f"{value:22} -> {valid:5} -> {message}")

    print("""
strict=True rejects an IPv4 network expression whose host bits are not zero.

For example:
    192.168.1.10/24

contains a host address rather than the canonical network address.

Using strict=False converts it to the containing network:
    192.168.1.0/24
""")


# =============================================================================
# SECTION 16: NETWORK MEMBERSHIP
# =============================================================================

def demonstrate_membership() -> None:
    print_title("16. NETWORK MEMBERSHIP")

    network = ipaddress.ip_network("192.168.100.0/24")

    candidates = [
        "192.168.100.1",
        "192.168.100.254",
        "192.168.101.1",
        "192.168.100.0",
        "192.168.100.255",
    ]

    print(f"Network: {network}")
    for candidate in candidates:
        ip = ipaddress.ip_address(candidate)
        print(f"{candidate:17} -> {'inside' if ip in network else 'outside'}")

    print("\nIPv6 membership:")
    ipv6_network = ipaddress.ip_network("2001:db8:1234::/48")
    for candidate in [
        "2001:db8:1234::1",
        "2001:db8:1234:abcd::1",
        "2001:db8:5678::1",
    ]:
        print(
            f"{candidate:30} -> "
            f"{'inside' if ipaddress.ip_address(candidate) in ipv6_network else 'outside'}"
        )


# =============================================================================
# SECTION 17: AGGREGATION AND SUMMARIZATION
# =============================================================================

def demonstrate_supernetting() -> None:
    print_title("17. ROUTE AGGREGATION AND SUMMARIZATION")

    networks = [
        ipaddress.ip_network("192.168.0.0/24"),
        ipaddress.ip_network("192.168.1.0/24"),
        ipaddress.ip_network("192.168.2.0/24"),
        ipaddress.ip_network("192.168.3.0/24"),
    ]

    print("Original networks:")
    for network in networks:
        print(f"  {network}")

    summary = list(ipaddress.collapse_addresses(networks))

    print("\nCollapsed representation:")
    for network in summary:
        print(f"  {network}")

    print("""
Route summarization reduces the number of routing entries by representing
multiple adjacent prefixes with a larger common prefix.

It is only correct when the summarized address space has the intended
contiguous structure and routing policy permits the aggregation.

Poor summarization can cause traffic to be sent toward a router that does
not actually have a more specific destination, so aggregation must be
designed together with routing topology.
""")


# =============================================================================
# SECTION 18: ADDRESS ALLOCATION HIERARCHY
# =============================================================================

def demonstrate_allocation_hierarchy() -> None:
    print_title("18. IP ALLOCATION HIERARCHY")

    print("""
A simplified global IPv4/IPv6 allocation model looks like:

    Global address registries
            |
            v
    Regional Internet Registries (RIRs)
            |
            v
    Internet Service Providers / large networks
            |
            v
    Organizations / customers
            |
            v
    Internal network allocation
            |
            v
    Hosts and interfaces

Examples of RIR regions include:

    AFRINIC  - Africa
    APNIC    - Asia Pacific
    ARIN     - North America and parts of the Caribbean
    LACNIC   - Latin America and parts of the Caribbean
    RIPE NCC - Europe, Middle East, and parts of Central Asia

Allocation is governed by registry policies and is not simply a matter of
choosing any unused public address.

Private IPv4 space is different: organizations may reuse RFC 1918 space
internally without obtaining unique public allocation for every internal
host.
""")


# =============================================================================
# SECTION 19: PUBLIC VS PRIVATE COMPARISON
# =============================================================================

def compare_public_private() -> None:
    print_title("19. PUBLIC IP VS PRIVATE IP")

    comparisons = [
        ("Global uniqueness", "Expected at Internet routing scale", "Can be reused by many organizations"),
        ("Internet routing", "May be globally routed subject to policy", "Not ordinarily globally routed as private space"),
        ("Typical use", "Internet-facing services and interfaces", "Internal LANs, servers, containers, VPCs/VNets"),
        ("NAT requirement", "Not inherently required", "Commonly translated for IPv4 Internet access"),
        ("Allocation", "Allocated through addressing policy/registries/providers", "Locally administered"),
    ]

    print(f"{'Property':25} | {'Public':45} | {'Private':45}")
    print("-" * 120)

    for property_name, public, private in comparisons:
        print(f"{property_name:25} | {public:45} | {private:45}")


# =============================================================================
# SECTION 20: IPv4 VS IPv6
# =============================================================================

def compare_ipv4_ipv6() -> None:
    print_title("20. IPv4 VS IPv6")

    comparisons = [
        ("Address size", "32 bits", "128 bits"),
        ("Typical notation", "Dotted decimal", "Colon-separated hexadecimal"),
        ("Broadcast", "Supported", "No broadcast; multicast is used"),
        ("Address space", "2^32", "2^128"),
        ("Common subnet size", "Varies widely", "/64 commonly used for IPv6 LAN subnets"),
        ("Private-style addressing", "RFC 1918", "Unique Local Addresses"),
        ("Link-local", "169.254.0.0/16", "fe80::/10"),
        ("Loopback", "127.0.0.0/8, commonly 127.0.0.1", "::1"),
        ("Configuration", "Static, DHCP, other mechanisms", "Static, DHCPv6, SLAAC, and combinations"),
        ("NAT dependence", "Common in IPv4 deployments", "Not fundamental to IPv6 addressing"),
    ]

    print(f"{'Property':22} | {'IPv4':45} | {'IPv6':45}")
    print("-" * 115)

    for property_name, ipv4, ipv6 in comparisons:
        print(f"{property_name:22} | {ipv4:45} | {ipv6:45}")


# =============================================================================
# SECTION 21: ADDRESS PLANNING
# =============================================================================

@dataclass
class NetworkPlan:
    site: str
    environment: str
    network: ipaddress._BaseNetwork
    purpose: str


def build_network_plan() -> list[NetworkPlan]:
    """
    Demonstrate a hierarchical enterprise addressing plan.

    The use of RFC 1918 addresses is deliberate because this is an internal
    planning example rather than a claim about publicly allocated space.
    """
    return [
        NetworkPlan(
            "Lucknow",
            "production",
            ipaddress.ip_network("10.10.0.0/20"),
            "application infrastructure",
        ),
        NetworkPlan(
            "Lucknow",
            "development",
            ipaddress.ip_network("10.10.16.0/20"),
            "development infrastructure",
        ),
        NetworkPlan(
            "Mumbai",
            "production",
            ipaddress.ip_network("10.20.0.0/20"),
            "application infrastructure",
        ),
        NetworkPlan(
            "Mumbai",
            "development",
            ipaddress.ip_network("10.20.16.0/20"),
            "development infrastructure",
        ),
    ]


def demonstrate_address_planning() -> None:
    print_title("21. HIERARCHICAL ADDRESS PLANNING")

    plans = build_network_plan()

    for plan in plans:
        print(
            f"{plan.site:10} | "
            f"{plan.environment:12} | "
            f"{str(plan.network):18} | "
            f"{plan.purpose}"
        )

    print("""
A scalable addressing plan usually considers:

    - geography
    - data center or availability zone
    - environment
    - business unit
    - application tier
    - security zone
    - routing domain
    - future growth

Hierarchical allocation makes summarization, troubleshooting, access control,
and documentation easier.

An address plan should reserve growth space instead of consuming every
available address immediately.
""")


# =============================================================================
# SECTION 22: SECURITY
# =============================================================================

def demonstrate_security_considerations() -> None:
    print_title("22. SECURITY CONSIDERATIONS")

    print("""
IP addressing is foundational to security controls but is not itself a
complete security boundary.

Important considerations:

1. IP addresses are identifiers, not reliable identities.
   A source address can be shared through NAT, changed through DHCP, or
   manipulated in attacks involving spoofing.

2. Private IP does not mean trusted.
   An internal address should not automatically bypass authentication or
   authorization.

3. Public IP does not automatically mean insecure.
   Security depends on routing, filtering, authentication, application
   controls, patching, encryption, and system configuration.

4. Network segmentation can reduce attack surface.
   Separate address spaces can support separation of workloads, but actual
   isolation requires routing and security policy.

5. Logs should preserve context.
   With NAT, the public source address alone may not identify an internal
   host. Source port, timestamp, NAT state, and other logging data may be
   required.

6. IPv6 must be included in security design.
   Deployments that filter IPv4 but accidentally expose IPv6 traffic can
   create inconsistent security policy.

7. Do not use documentation prefixes as production Internet identities.
   Ranges such as 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24 and
   2001:db8::/32 are intended for documentation and examples.
""")


# =============================================================================
# SECTION 23: PERFORMANCE AND ALGORITHMIC CONSIDERATIONS
# =============================================================================

def benchmark_membership_operations() -> None:
    print_title("23. PERFORMANCE CONSIDERATIONS")

    networks = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/16"),
        ipaddress.ip_network("10.1.0.0/24"),
        ipaddress.ip_network("10.1.1.0/28"),
    ]

    destinations = [
        ipaddress.ip_address("10.1.1.5"),
        ipaddress.ip_address("10.1.2.5"),
        ipaddress.ip_address("10.2.3.4"),
        ipaddress.ip_address("192.168.1.1"),
    ]

    for destination in destinations:
        matches = [network for network in networks if destination in network]
        print(f"{destination:15} -> {matches}")

    print("""
For a small routing table, scanning every route is easy to understand.

Large routing systems need data structures optimized for prefix matching,
such as:

    - radix trees
    - Patricia tries
    - specialized prefix tables
    - hardware forwarding tables

A longest-prefix-match operation is conceptually simple but can become a
significant systems-engineering problem at large scale.
""")


# =============================================================================
# SECTION 24: EDGE CASES
# =============================================================================

def demonstrate_edge_cases() -> None:
    print_title("24. IMPORTANT EDGE CASES")

    cases = [
        ("IPv4 /32", "192.0.2.10/32"),
        ("IPv4 /31", "192.0.2.10/31"),
        ("IPv4 /30", "192.0.2.8/30"),
        ("IPv6 /128", "2001:db8::10/128"),
        ("IPv6 /127", "2001:db8::10/127"),
        ("IPv6 /64", "2001:db8:abcd:1::/64"),
        ("IPv6 /0", "::/0"),
    ]

    for name, cidr in cases:
        interface = ipaddress.ip_interface(cidr)
        network = interface.network

        print(
            f"{name:12} | {network!s:30} | "
            f"addresses={network.num_addresses:,}"
        )

    print("""
Important edge cases include:

    /0
        Matches every address of the corresponding IP version. In routing,
        this commonly represents a default route.

    /32 IPv4 or /128 IPv6
        Represents one address.

    /31 IPv4
        Can represent a point-to-point link under RFC 3021.

    IPv6 /127
        Is used in some point-to-point designs, subject to operational
        conventions and implementation considerations.

    Network address vs host address
        An address can be syntactically valid but still unsuitable for a
        particular role.
""")


# =============================================================================
# SECTION 25: ADDRESS ITERATION WITHOUT EXCESSIVE MEMORY
# =============================================================================

def demonstrate_large_network_iteration() -> None:
    print_title("25. LARGE NETWORKS AND MEMORY")

    network = ipaddress.ip_network("2001:db8::/120")

    print(f"Network: {network}")
    print(f"Address count: {network.num_addresses:,}")

    print("First five addresses:")
    for address in itertools.islice(network, 5):
        print(f"  {address}")

    print("""
The ipaddress module provides iterable network objects.

For very large IPv6 networks, materializing every address into a list can
consume enormous amounts of memory.

Prefer:
    - iteration
    - generators
    - prefix-based data structures
    - database-backed allocation

rather than creating massive in-memory address lists.
""")


# =============================================================================
# SECTION 26: ALLOCATION SIMULATION
# =============================================================================

def simulate_host_allocation(network: str, requested: int, seed: int = 42) -> list[str]:
    """
    Educational simulation of selecting available IPv4 host addresses.

    The function samples from the host range without changing network policy.
    """
    rng = random.Random(seed)
    ipv4_network = ipaddress.ip_network(network)

    hosts = list(ipv4_network.hosts())

    if requested > len(hosts):
        raise ValueError("Requested more hosts than the network can provide.")

    selected = rng.sample(hosts, requested)
    return [str(address) for address in selected]


def demonstrate_simulation() -> None:
    print_title("26. ADDRESS ALLOCATION SIMULATION")

    allocated = simulate_host_allocation("192.168.200.0/24", 8)

    for index, address in enumerate(allocated, start=1):
        print(f"Host {index:02}: {address}")

    print("""
Production allocation should not randomly select addresses.

Real systems maintain authoritative state so that:
    - duplicate allocation is prevented
    - reservations are honored
    - leases are tracked
    - ownership is recorded
    - conflicts can be detected

The random example is only useful for demonstrating address selection.
""")


# =============================================================================
# SECTION 27: COMMON MISTAKES
# =============================================================================

def demonstrate_common_mistakes() -> None:
    print_title("27. COMMON MISTAKES")

    mistakes = [
        (
            "Treating every 192.168.x.x address as globally reachable",
            "192.168.0.0/16 is private IPv4 space."
        ),
        (
            "Assuming private means secure",
            "Security requires explicit controls and policy."
        ),
        (
            "Forgetting IPv6",
            "A host may have both IPv4 and IPv6 connectivity."
        ),
        (
            "Confusing subnet mask with gateway",
            "A subnet mask/prefix defines address structure; a gateway is a routing endpoint."
        ),
        (
            "Using documentation prefixes in production",
            "Documentation ranges are intended for examples."
        ),
        (
            "Ignoring overlap",
            "Overlapping network ranges can cause ambiguous routing and operational failures."
        ),
        (
            "Assuming all /24 networks have exactly 254 usable hosts",
            "That is a traditional model and does not apply universally, especially to /31 and /32."
        ),
        (
            "Assuming IPv6 has broadcast",
            "IPv6 uses multicast rather than broadcast."
        ),
    ]

    for mistake, correction in mistakes:
        print(f"\nMistake:    {mistake}")
        print(f"Correction: {correction}")


# =============================================================================
# SECTION 28: COMPREHENSIVE SELF-TEST
# =============================================================================

def run_self_tests() -> None:
    print_title("28. SELF-TESTS")

    assert ipv4_to_binary("255.255.255.255") == "1" * 32
    assert binary_to_ipv4("0" * 32) == "0.0.0.0"

    assert is_rfc1918_private_ipv4("10.1.2.3")
    assert is_rfc1918_private_ipv4("172.16.1.1")
    assert is_rfc1918_private_ipv4("192.168.1.1")
    assert not is_rfc1918_private_ipv4("172.15.1.1")
    assert not is_rfc1918_private_ipv4("8.8.8.8")

    assert ipaddress.ip_address("127.0.0.1").is_loopback
    assert ipaddress.ip_address("224.0.0.1").is_multicast
    assert ipaddress.ip_address("::1").is_loopback
    assert ipaddress.ip_address("fe80::1").is_link_local

    route_table = RoutingTable()
    route_table.add_route("0.0.0.0/0", "default")
    route_table.add_route("10.0.0.0/8", "A")
    route_table.add_route("10.1.0.0/16", "B")
    route_table.add_route("10.1.2.0/24", "C")

    assert route_table.lookup("10.1.2.50").next_hop == "C"
    assert route_table.lookup("10.1.50.50").next_hop == "B"
    assert route_table.lookup("10.2.50.50").next_hop == "A"
    assert route_table.lookup("8.8.8.8").next_hop == "default"

    assert ipaddress.ip_address("192.168.1.10") in ipaddress.ip_network("192.168.1.0/24")
    assert ipaddress.ip_address("192.168.2.10") not in ipaddress.ip_network("192.168.1.0/24")

    print("All self-tests passed.")


# =============================================================================
# SECTION 29: INTERACTIVE IP ADDRESS INSPECTOR
# =============================================================================

def interactive_inspector() -> None:
    print_title("29. OPTIONAL INTERACTIVE IP INSPECTOR")

    print("Enter an IPv4 or IPv6 address, or press Enter to skip.")

    value = input("IP address: ").strip()

    if not value:
        print("Interactive inspection skipped.")
        return

    try:
        ip = ipaddress.ip_address(value)
    except ValueError as exc:
        print(f"Invalid address: {exc}")
        return

    print(f"\nAddress:       {ip}")
    print(f"Version:       IPv{ip.version}")
    print(f"Compressed:    {ip.compressed}")

    if ip.version == 6:
        print(f"Exploded:      {ip.exploded}")

    print(f"Private:       {ip.is_private}")
    print(f"Global:        {ip.is_global}")
    print(f"Loopback:      {ip.is_loopback}")
    print(f"Link-local:    {ip.is_link_local}")
    print(f"Multicast:     {ip.is_multicast}")
    print(f"Unspecified:   {ip.is_unspecified}")
    print(f"Reserved:      {ip.is_reserved}")

    if ip.version == 4:
        print(f"RFC1918:       {is_rfc1918_private_ipv4(value)}")

    print(f"Special ranges: {ranges_containing(value)}")


# =============================================================================
# SECTION 30: MAIN
# =============================================================================

def main() -> None:
    print_title("IP ADDRESSING COMPLETE STUDY PROGRAM")

    explain_ip_basics()
    demonstrate_binary()
    demonstrate_subnetting()
    demonstrate_classification()
    demonstrate_private_ranges()
    demonstrate_nat()
    demonstrate_special_ranges()
    demonstrate_ipv6()
    demonstrate_ipv6_scopes()
    demonstrate_subnet_math()
    demonstrate_vlsm()
    demonstrate_ipam()
    demonstrate_dhcp()
    demonstrate_routing()
    demonstrate_validation()
    demonstrate_membership()
    demonstrate_supernetting()
    demonstrate_allocation_hierarchy()
    compare_public_private()
    compare_ipv4_ipv6()
    demonstrate_address_planning()
    demonstrate_security_considerations()
    benchmark_membership_operations()
    demonstrate_edge_cases()
    demonstrate_large_network_iteration()
    demonstrate_simulation()
    demonstrate_common_mistakes()
    run_self_tests()

    # The inspector is intentionally available but not automatically invoked,
    # so the script remains non-interactive and suitable for automation.
    print("\nInteractive inspector is available through interactive_inspector().")
    print("Call main() to execute the complete educational demonstration.")


if __name__ == "__main__":
    main()
