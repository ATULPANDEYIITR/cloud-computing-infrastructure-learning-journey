#!/usr/bin/env python3
"""
Subnetting and CIDR
===================

A self-contained study and demonstration program covering:

- IPv4 addresses and binary representation
- Network masks and subnet masks
- CIDR notation
- Prefix lengths
- Network and broadcast addresses
- Usable host ranges
- Number of subnets and hosts
- Fixed-length subnetting
- VLSM concepts
- Private IPv4 ranges
- Special cases such as /31 and /32
- Address validation
- Subnet membership
- Range overlap detection
- Route summarization
- Longest-prefix matching
- Practical subnet allocation
- Error handling and edge cases

The program uses only Python's standard library.
"""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network, IPv4Interface
from typing import Iterable


# ---------------------------------------------------------------------------
# FUNDAMENTALS
# ---------------------------------------------------------------------------

def ipv4_to_binary(address: str) -> str:
    """Return an IPv4 address as four 8-bit binary octets."""
    ip = IPv4Address(address)
    return ".".join(f"{octet:08b}" for octet in ip.packed)


def binary_to_ipv4(binary: str) -> str:
    """Convert a 32-bit binary IPv4 string to dotted decimal notation."""
    cleaned = binary.replace(".", "").replace(" ", "")

    if len(cleaned) != 32 or any(bit not in "01" for bit in cleaned):
        raise ValueError("Binary IPv4 input must contain exactly 32 binary bits.")

    octets = [
        str(int(cleaned[index:index + 8], 2))
        for index in range(0, 32, 8)
    ]
    return ".".join(octets)


def prefix_to_mask(prefix: int) -> IPv4Address:
    """Convert a CIDR prefix length into a dotted-decimal subnet mask."""
    if not 0 <= prefix <= 32:
        raise ValueError("Prefix length must be between 0 and 32.")

    if prefix == 0:
        mask = 0
    else:
        mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF

    return IPv4Address(mask)


def mask_to_prefix(mask: str) -> int:
    """Convert a dotted-decimal subnet mask into its CIDR prefix."""
    address = IPv4Address(mask)
    binary = f"{int(address):032b}"

    # A valid subnet mask contains contiguous ones followed by zeros.
    if "01" in binary:
        raise ValueError(f"{mask} is not a valid contiguous subnet mask.")

    return binary.count("1")


# ---------------------------------------------------------------------------
# BASIC CIDR CALCULATIONS
# ---------------------------------------------------------------------------

def usable_host_count(prefix: int) -> int:
    """
    Calculate conventional usable IPv4 hosts.

    /31 and /32 are handled specially:
    - /31 is commonly used for point-to-point links and has two usable
      addresses under RFC 3021 semantics.
    - /32 represents exactly one address and has one usable address.
    """
    if not 0 <= prefix <= 32:
        raise ValueError("Prefix length must be between 0 and 32.")

    total = 2 ** (32 - prefix)

    if prefix == 31:
        return 2
    if prefix == 32:
        return 1

    return max(total - 2, 0)


def conventional_host_count(prefix: int) -> int:
    """Return the traditional host count using network/broadcast exclusion."""
    if not 0 <= prefix <= 32:
        raise ValueError("Prefix length must be between 0 and 32.")

    total = 2 ** (32 - prefix)

    if prefix >= 31:
        return 0

    return total - 2


def subnet_count(parent_prefix: int, child_prefix: int) -> int:
    """Calculate how many equal-sized child subnets fit inside a parent."""
    if not 0 <= parent_prefix <= 32:
        raise ValueError("Parent prefix must be between 0 and 32.")
    if not 0 <= child_prefix <= 32:
        raise ValueError("Child prefix must be between 0 and 32.")
    if child_prefix < parent_prefix:
        raise ValueError("Child prefix must be equal to or longer than parent.")

    return 2 ** (child_prefix - parent_prefix)


def analyze_network(cidr: str) -> dict:
    """
    Return detailed information about an IPv4 CIDR network.

    strict=False permits inputs such as 192.168.1.25/24 and normalizes them
    to 192.168.1.0/24.
    """
    network = IPv4Network(cidr, strict=False)

    return {
        "input": cidr,
        "network": str(network),
        "network_address": str(network.network_address),
        "broadcast_address": str(network.broadcast_address),
        "prefix": network.prefixlen,
        "subnet_mask": str(network.netmask),
        "wildcard_mask": str(network.hostmask),
        "total_addresses": network.num_addresses,
        "usable_hosts_conventional": conventional_host_count(network.prefixlen),
        "usable_hosts_rfc3021_aware": usable_host_count(network.prefixlen),
        "first_address": str(network[0]),
        "last_address": str(network[-1]),
        "is_private": network.is_private,
        "is_global": network.is_global,
        "is_loopback": network.is_loopback,
        "is_link_local": network.is_link_local,
        "is_multicast": network.is_multicast,
    }


def print_network_analysis(cidr: str) -> None:
    """Print a readable network analysis."""
    data = analyze_network(cidr)

    print(f"\nNetwork analysis: {data['input']}")
    print("-" * 60)

    for key, value in data.items():
        if key != "input":
            print(f"{key:32}: {value}")


# ---------------------------------------------------------------------------
# SUBNET MEMBERSHIP
# ---------------------------------------------------------------------------

def address_belongs_to_subnet(address: str, cidr: str) -> bool:
    """Return True when an address belongs to a CIDR network."""
    return IPv4Address(address) in IPv4Network(cidr, strict=False)


def subnet_contains_subnet(parent: str, child: str) -> bool:
    """Return True if the entire child network is inside the parent."""
    return IPv4Network(child, strict=False).subnet_of(
        IPv4Network(parent, strict=False)
    )


def networks_overlap(first: str, second: str) -> bool:
    """Return True if two IPv4 networks overlap."""
    a = IPv4Network(first, strict=False)
    b = IPv4Network(second, strict=False)

    return a.overlaps(b)


# ---------------------------------------------------------------------------
# SUBNET ENUMERATION
# ---------------------------------------------------------------------------

def split_network(cidr: str, new_prefix: int) -> list[IPv4Network]:
    """
    Divide a network into equal-sized subnets.

    Example:
        192.168.1.0/24 -> /26
        produces four /26 networks.
    """
    network = IPv4Network(cidr, strict=False)

    if new_prefix < network.prefixlen:
        raise ValueError("New prefix cannot be shorter than parent prefix.")

    if new_prefix > 32:
        raise ValueError("Prefix cannot exceed /32.")

    return list(network.subnets(new_prefix=new_prefix))


def display_subnets(cidr: str, new_prefix: int) -> None:
    """Print all child subnets."""
    subnets = split_network(cidr, new_prefix)

    print(
        f"\nSplitting {IPv4Network(cidr, strict=False)} "
        f"into /{new_prefix} subnets"
    )
    print("-" * 60)

    for number, subnet in enumerate(subnets, start=1):
        print(
            f"{number:3}. {subnet} | "
            f"network={subnet.network_address} | "
            f"broadcast={subnet.broadcast_address} | "
            f"hosts={usable_host_count(subnet.prefixlen)}"
        )


# ---------------------------------------------------------------------------
# VLSM
# ---------------------------------------------------------------------------

def required_prefix(host_requirement: int) -> int:
    """
    Find the smallest conventional IPv4 subnet that can hold the requested
    number of usable hosts.

    For normal LAN-style subnets, two addresses are reserved:
    network address and broadcast address.
    """
    if host_requirement < 1:
        raise ValueError("Host requirement must be positive.")

    for prefix in range(30, -1, -1):
        if conventional_host_count(prefix) >= host_requirement:
            return prefix

    raise ValueError("Requirement cannot be represented by an IPv4 subnet.")


@dataclass(frozen=True)
class VLSMRequirement:
    name: str
    hosts: int


@dataclass
class VLSMAllocation:
    name: str
    requested_hosts: int
    network: IPv4Network
    usable_hosts: int


def allocate_vlsm(
    parent_cidr: str,
    requirements: Iterable[VLSMRequirement],
) -> list[VLSMAllocation]:
    """
    Allocate variable-sized subnets from a parent network.

    Requirements are sorted from largest to smallest because VLSM normally
    allocates the largest blocks first to reduce fragmentation.
    """
    parent = IPv4Network(parent_cidr, strict=False)

    ordered = sorted(
        requirements,
        key=lambda item: item.hosts,
        reverse=True,
    )

    allocations: list[VLSMAllocation] = []
    cursor = int(parent.network_address)

    for requirement in ordered:
        prefix = required_prefix(requirement.hosts)
        block_size = 2 ** (32 - prefix)

        # Align the next allocation to the required block boundary.
        if cursor % block_size != 0:
            cursor = ((cursor // block_size) + 1) * block_size

        candidate = IPv4Network(
            f"{IPv4Address(cursor)}/{prefix}",
            strict=False,
        )

        if not candidate.subnet_of(parent):
            raise ValueError(
                f"Requirement '{requirement.name}' does not fit "
                f"inside {parent}."
            )

        allocations.append(
            VLSMAllocation(
                name=requirement.name,
                requested_hosts=requirement.hosts,
                network=candidate,
                usable_hosts=conventional_host_count(prefix),
            )
        )

        cursor = int(candidate.broadcast_address) + 1

    return allocations


def print_vlsm_allocations(
    parent_cidr: str,
    requirements: Iterable[VLSMRequirement],
) -> None:
    """Display a VLSM allocation plan."""
    allocations = allocate_vlsm(parent_cidr, requirements)

    print(f"\nVLSM allocation inside {IPv4Network(parent_cidr, strict=False)}")
    print("-" * 90)

    for allocation in allocations:
        print(
            f"{allocation.name:15} "
            f"requested={allocation.requested_hosts:5} "
            f"network={str(allocation.network):18} "
            f"usable={allocation.usable_hosts:5} "
            f"range={allocation.network.network_address} - "
            f"{allocation.network.broadcast_address}"
        )


# ---------------------------------------------------------------------------
# ROUTE SUMMARIZATION
# ---------------------------------------------------------------------------

def summarize_networks(cidrs: Iterable[str]) -> list[IPv4Network]:
    """
    Summarize adjacent or related networks into the smallest possible
    collection of CIDR blocks.
    """
    networks = [
        IPv4Network(cidr, strict=False)
        for cidr in cidrs
    ]

    return list(__import__("ipaddress").collapse_addresses(networks))


def print_summaries(cidrs: Iterable[str]) -> None:
    """Display CIDR route summarization."""
    networks = list(cidrs)
    summarized = summarize_networks(networks)

    print("\nRoute summarization")
    print("-" * 60)
    print("Input:")
    for network in networks:
        print(f"  {network}")

    print("Summarized:")
    for network in summarized:
        print(f"  {network}")


# ---------------------------------------------------------------------------
# LONGEST PREFIX MATCHING
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Route:
    network: IPv4Network
    next_hop: str


def longest_prefix_match(
    destination: str,
    routes: Iterable[Route],
) -> Route | None:
    """
    Select the matching route with the longest prefix.

    This models the core rule used by IP routing:
    among matching routes, the most specific prefix wins.
    """
    address = IPv4Address(destination)

    matches = [
        route
        for route in routes
        if address in route.network
    ]

    if not matches:
        return None

    return max(matches, key=lambda route: route.network.prefixlen)


# ---------------------------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------------------------

def validate_cidr(cidr: str) -> tuple[bool, str]:
    """Validate CIDR notation without allowing malformed input to escape."""
    try:
        network = IPv4Network(cidr, strict=False)
        return True, f"Valid IPv4 CIDR: {network}"
    except ValueError as error:
        return False, f"Invalid CIDR: {error}"


def demonstrate_validation() -> None:
    """Demonstrate valid and invalid CIDR values."""
    examples = [
        "192.168.1.0/24",
        "10.0.0.0/8",
        "172.16.5.10/16",
        "192.168.1.0/33",
        "192.168.1.256/24",
        "192.168.1.0/255.255.255.0",
        "not-an-ip/24",
    ]

    print("\nCIDR validation")
    print("-" * 60)

    for example in examples:
        valid, message = validate_cidr(example)
        print(f"{example:28} -> {message}")


# ---------------------------------------------------------------------------
# ADDRESS INTERFACES
# ---------------------------------------------------------------------------

def demonstrate_interface() -> None:
    """
    IPv4Interface represents an address plus its prefix.

    This differs conceptually from IPv4Network:
    an interface describes an endpoint's assigned address,
    while a network describes the complete subnet.
    """
    interface = IPv4Interface("192.168.20.37/27")

    print("\nIPv4 interface example")
    print("-" * 60)
    print(f"Address       : {interface.ip}")
    print(f"Network       : {interface.network}")
    print(f"Prefix        : /{interface.network.prefixlen}")
    print(f"Subnet mask   : {interface.network.netmask}")
    print(f"Broadcast     : {interface.network.broadcast_address}")
    print(f"Host address? : {interface.ip != interface.network.network_address}")


# ---------------------------------------------------------------------------
# MANUAL BITWISE CALCULATION
# ---------------------------------------------------------------------------

def manual_network_address(address: str, mask: str) -> str:
    """
    Calculate a network address using integer bitwise AND.

    This exposes the fundamental mathematical mechanism behind subnetting:
        network = address AND subnet_mask
    """
    ip_value = int(IPv4Address(address))
    mask_value = int(IPv4Address(mask))

    network_value = ip_value & mask_value

    return str(IPv4Address(network_value))


def manual_broadcast_address(address: str, mask: str) -> str:
    """
    Calculate broadcast using:

        broadcast = network OR inverted_mask
    """
    network_value = int(IPv4Address(address)) & int(IPv4Address(mask))
    mask_value = int(IPv4Address(mask))
    wildcard_value = mask_value ^ 0xFFFFFFFF

    broadcast_value = network_value | wildcard_value

    return str(IPv4Address(broadcast_value))


def demonstrate_bitwise_math() -> None:
    """Demonstrate the bit-level subnet calculation."""
    address = "192.168.10.77"
    mask = "255.255.255.192"

    print("\nManual bitwise subnet calculation")
    print("-" * 60)
    print(f"Address : {address}")
    print(f"Binary  : {ipv4_to_binary(address)}")
    print(f"Mask    : {mask}")
    print(f"Binary  : {ipv4_to_binary(mask)}")
    print(f"Network : {manual_network_address(address, mask)}")
    print(f"Broadcast: {manual_broadcast_address(address, mask)}")


# ---------------------------------------------------------------------------
# SPECIAL CASES
# ---------------------------------------------------------------------------

def demonstrate_special_prefixes() -> None:
    """Explain the practical meaning of /0, /31, and /32."""
    prefixes = [0, 8, 16, 24, 30, 31, 32]

    print("\nImportant prefix lengths")
    print("-" * 60)

    for prefix in prefixes:
        mask = prefix_to_mask(prefix)
        total = 2 ** (32 - prefix)

        print(
            f"/{prefix:2}  "
            f"mask={mask!s:15} "
            f"total={total:12} "
            f"conventional_hosts={conventional_host_count(prefix):12} "
            f"special-aware_hosts={usable_host_count(prefix):12}"
        )


# ---------------------------------------------------------------------------
# PRACTICAL NETWORK DESIGN CASE STUDY
# ---------------------------------------------------------------------------

def enterprise_network_case_study() -> None:
    """
    Model a small organization's address plan.

    The organization receives 10.50.0.0/16 and needs separate networks for:

    - Engineering
    - Operations
    - Finance
    - Guest Wi-Fi
    - Servers
    - Point-to-point infrastructure

    VLSM avoids wasting a /24 on every department.
    """
    requirements = [
        VLSMRequirement("Engineering", 500),
        VLSMRequirement("Operations", 200),
        VLSMRequirement("Guest-WiFi", 100),
        VLSMRequirement("Servers", 60),
        VLSMRequirement("Finance", 30),
        VLSMRequirement("Network-P2P", 2),
    ]

    print_vlsm_allocations("10.50.0.0/16", requirements)


# ---------------------------------------------------------------------------
# COMPARISON EXAMPLES
# ---------------------------------------------------------------------------

def compare_subnet_sizes() -> None:
    """Compare common subnet sizes and their address capacity."""
    prefixes = [8, 16, 20, 22, 24, 25, 26, 27, 28, 29, 30]

    print("\nSubnet size comparison")
    print("-" * 75)
    print(
        f"{'Prefix':>8} {'Mask':>18} {'Total':>12} "
        f"{'Conventional usable':>22}"
    )

    for prefix in prefixes:
        print(
            f"/{prefix:<7} "
            f"{str(prefix_to_mask(prefix)):>18} "
            f"{2 ** (32 - prefix):>12} "
            f"{conventional_host_count(prefix):>22}"
        )


# ---------------------------------------------------------------------------
# EDGE CASES
# ---------------------------------------------------------------------------

def demonstrate_edge_cases() -> None:
    """Demonstrate non-canonical inputs, boundaries, and membership."""
    print("\nEdge cases")
    print("-" * 60)

    cases = [
        ("192.168.1.99/24", "192.168.1.99"),
        ("10.0.0.0/8", "10.255.255.255"),
        ("172.16.0.0/16", "172.17.0.1"),
        ("192.168.10.0/31", "192.168.10.1"),
        ("192.168.10.10/32", "192.168.10.10"),
    ]

    for cidr, address in cases:
        network = IPv4Network(cidr, strict=False)
        print(
            f"{address:16} in {str(network):18} -> "
            f"{address_belongs_to_subnet(address, cidr)}"
        )

    print("\nNetwork containment:")
    print(
        "10.0.0.0/8 contains 10.20.0.0/16 ->",
        subnet_contains_subnet("10.0.0.0/8", "10.20.0.0/16"),
    )
    print(
        "10.20.0.0/16 contains 10.0.0.0/8 ->",
        subnet_contains_subnet("10.20.0.0/16", "10.0.0.0/8"),
    )

    print("\nOverlap:")
    print(
        "192.168.0.0/24 vs 192.168.0.128/25 ->",
        networks_overlap("192.168.0.0/24", "192.168.0.128/25"),
    )
    print(
        "192.168.0.0/24 vs 192.168.1.0/24 ->",
        networks_overlap("192.168.0.0/24", "192.168.1.0/24"),
    )


# ---------------------------------------------------------------------------
# ROUTING CASE STUDY
# ---------------------------------------------------------------------------

def routing_case_study() -> None:
    """Demonstrate longest-prefix route selection."""
    routes = [
        Route(IPv4Network("0.0.0.0/0"), "Internet gateway"),
        Route(IPv4Network("10.0.0.0/8"), "Core router A"),
        Route(IPv4Network("10.20.0.0/16"), "Core router B"),
        Route(IPv4Network("10.20.30.0/24"), "Distribution router C"),
        Route(IPv4Network("10.20.30.128/25"), "Access router D"),
    ]

    destinations = [
        "8.8.8.8",
        "10.1.2.3",
        "10.20.5.10",
        "10.20.30.25",
        "10.20.30.200",
    ]

    print("\nLongest-prefix matching")
    print("-" * 60)

    for destination in destinations:
        route = longest_prefix_match(destination, routes)

        if route:
            print(
                f"{destination:16} -> "
                f"{route.network!s:18} -> {route.next_hop}"
            )
        else:
            print(f"{destination:16} -> no route")


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------

def run_tests() -> None:
    """Run lightweight built-in assertions."""
    assert prefix_to_mask(24) == IPv4Address("255.255.255.0")
    assert mask_to_prefix("255.255.255.0") == 24
    assert ipv4_to_binary("192.168.1.1") == (
        "11000000.10101000.00000001.00000001"
    )
    assert binary_to_ipv4(
        "11000000.10101000.00000001.00000001"
    ) == "192.168.1.1"

    assert manual_network_address(
        "192.168.10.77",
        "255.255.255.192",
    ) == "192.168.10.64"

    assert manual_broadcast_address(
        "192.168.10.77",
        "255.255.255.192",
    ) == "192.168.10.127"

    assert usable_host_count(24) == 254
    assert usable_host_count(31) == 2
    assert usable_host_count(32) == 1

    assert len(split_network("192.168.1.0/24", 26)) == 4
    assert address_belongs_to_subnet(
        "192.168.1.100",
        "192.168.1.0/24",
    )

    assert not address_belongs_to_subnet(
        "192.168.2.100",
        "192.168.1.0/24",
    )

    assert subnet_contains_subnet(
        "10.0.0.0/8",
        "10.1.0.0/16",
    )

    assert networks_overlap(
        "192.168.0.0/24",
        "192.168.0.128/25",
    )

    summarized = summarize_networks(
        [
            "192.168.0.0/25",
            "192.168.0.128/25",
        ]
    )

    assert summarized == [IPv4Network("192.168.0.0/24")]

    routes = [
        Route(IPv4Network("10.0.0.0/8"), "A"),
        Route(IPv4Network("10.10.0.0/16"), "B"),
        Route(IPv4Network("10.10.20.0/24"), "C"),
    ]

    selected = longest_prefix_match("10.10.20.50", routes)

    assert selected is not None
    assert selected.next_hop == "C"

    print("\nAll built-in tests passed.")


# ---------------------------------------------------------------------------
# MAIN STUDY PROGRAM
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 80)
    print("SUBNETTING AND CIDR - COMPREHENSIVE PYTHON STUDY PROGRAM")
    print("=" * 80)

    print("\n1. IPv4 binary representation")
    print("-" * 60)
    example_address = "192.168.10.77"
    print(f"Address: {example_address}")
    print(f"Binary : {ipv4_to_binary(example_address)}")

    print("\n2. CIDR network analysis")
    print_network_analysis("192.168.10.77/26")

    print("\n3. Common subnet sizes")
    compare_subnet_sizes()

    print("\n4. Fixed-length subnetting")
    display_subnets("192.168.50.0/24", 26)

    print("\n5. Bitwise subnet mathematics")
    demonstrate_bitwise_math()

    print("\n6. Address and interface semantics")
    demonstrate_interface()

    print("\n7. Validation")
    demonstrate_validation()

    print("\n8. Special prefix lengths")
    demonstrate_special_prefixes()

    print("\n9. Edge cases")
    demonstrate_edge_cases()

    print("\n10. VLSM enterprise case study")
    enterprise_network_case_study()

    print("\n11. Route summarization")
    print_summaries(
        [
            "10.100.0.0/24",
            "10.100.1.0/24",
            "10.100.2.0/24",
            "10.100.3.0/24",
        ]
    )

    print("\n12. Routing")
    routing_case_study()

    print("\n13. Verification")
    run_tests()

    print("\nStudy program completed.")


if __name__ == "__main__":
    main()
