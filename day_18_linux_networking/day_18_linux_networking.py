#!/usr/bin/env python3
"""
Linux Networking: interfaces, IP addresses, DNS configuration, routing basics,
and ports, with practical demonstrations of ip, ping, ss, and netstat.

This study script is designed to run on Linux. Most commands are read-only.
Some sections gracefully handle missing commands, permissions, unavailable
interfaces, and unreachable hosts.

Run:
    python3 linux_networking.py

The script does not modify networking configuration. Commands that can change
system state are discussed in comments and demonstrations, but are not
executed automatically.
"""

from __future__ import annotations

import ipaddress
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def print_section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def print_subsection(title: str) -> None:
    print(f"\n--- {title} ---")


def command_exists(command: str) -> bool:
    """Return True when an executable is available in PATH."""
    return shutil.which(command) is not None


def run_command(
    command: list[str],
    timeout: int = 5,
    allow_failure: bool = True,
) -> tuple[int, str, str]:
    """
    Execute a command safely and return:
        (return_code, stdout, stderr)

    shell=True is deliberately avoided so arguments are passed directly.
    """
    if not command or not command_exists(command[0]):
        return 127, "", f"Command not found: {command[0] if command else '<empty>'}"

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", "Command timed out."
    except OSError as exc:
        return 1, "", str(exc)

    if not allow_failure and result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(command)}\n{result.stderr.strip()}"
        )

    return result.returncode, result.stdout, result.stderr


def print_command(command: list[str], timeout: int = 5) -> None:
    """Run a command and display its result."""
    print(f"$ {' '.join(command)}")
    code, stdout, stderr = run_command(command, timeout=timeout)

    if stdout.strip():
        print(stdout.rstrip())

    if stderr.strip():
        print(f"[stderr] {stderr.rstrip()}")

    if code != 0:
        print(f"[exit code: {code}]")


# ---------------------------------------------------------------------------
# 1. Fundamental networking concepts
# ---------------------------------------------------------------------------

def explain_fundamentals() -> None:
    print_section("1. Linux networking fundamentals")

    print(
        """
A Linux network connection can be understood as several cooperating layers:

  Application
      |
      | HTTP, HTTPS, SSH, DNS, etc.
      v
  Transport
      |
      | TCP or UDP
      | Ports identify application endpoints.
      v
  Internet
      |
      | IPv4 or IPv6 addresses
      | Routers forward packets between networks.
      v
  Link
      |
      | Ethernet, Wi-Fi, virtual interfaces, bridges, etc.
      v
  Physical / virtual network medium

Important terms:

  Network interface
      A Linux object representing a network connection point. Examples include
      Ethernet interfaces, Wi-Fi interfaces, loopback, bridges, and virtual
      interfaces.

  MAC address
      A link-layer address normally associated with Ethernet/Wi-Fi interfaces.

  IP address
      A logical address used at the Internet layer. IPv4 uses 32 bits;
      IPv6 uses 128 bits.

  Subnet prefix
      The portion of an address identifying a network. For example,
      192.168.1.25/24 means the first 24 bits identify the network.

  Default gateway
      A router used when the destination is not covered by a more specific
      local route.

  DNS
      The Domain Name System maps names such as example.com to IP addresses
      and supports other records such as MX, TXT, CNAME, and AAAA.

  Port
      A 16-bit transport-layer identifier from 0 through 65535. TCP and UDP
      have independent port spaces.

  Socket
      An operating-system communication endpoint. A listening TCP socket
      commonly consists of a local address and local port and waits for
      incoming connections.

  Routing table
      A set of rules used to determine where packets should be sent.

The same machine can have several interfaces and several IP addresses.
The interface chosen for a packet depends on routing, not simply on the
destination's textual appearance.
"""
    )


# ---------------------------------------------------------------------------
# 2. IP address calculations
# ---------------------------------------------------------------------------

def demonstrate_ip_addresses() -> None:
    print_section("2. IP addresses and subnetting")

    examples = [
        "127.0.0.1",
        "192.168.1.25/24",
        "10.10.20.15/16",
        "172.16.5.20/20",
        "2001:db8::10/64",
        "::1",
    ]

    for value in examples:
        try:
            if "/" in value:
                interface = ipaddress.ip_interface(value)
                print(
                    f"{value:24} "
                    f"version={interface.version} "
                    f"address={interface.ip} "
                    f"network={interface.network} "
                    f"private={interface.is_private}"
                )
            else:
                address = ipaddress.ip_address(value)
                print(
                    f"{value:24} "
                    f"version={address.version} "
                    f"loopback={address.is_loopback} "
                    f"private={address.is_private} "
                    f"multicast={address.is_multicast}"
                )
        except ValueError as exc:
            print(f"{value}: invalid address: {exc}")

    print_subsection("Subnet membership")

    network = ipaddress.ip_network("192.168.50.0/24")
    candidates = [
        ipaddress.ip_address("192.168.50.1"),
        ipaddress.ip_address("192.168.50.200"),
        ipaddress.ip_address("192.168.51.10"),
    ]

    for address in candidates:
        print(f"{address} in {network}: {address in network}")

    print_subsection("IPv4 address categories")

    category_examples = {
        "Loopback": "127.0.0.1",
        "Private RFC1918": "10.0.0.1",
        "Private RFC1918": "172.16.0.1",
        "Private RFC1918": "192.168.1.1",
        "IPv6 loopback": "::1",
        "Documentation IPv4": "192.0.2.1",
        "Documentation IPv6": "2001:db8::1",
    }

    for label, value in category_examples.items():
        address = ipaddress.ip_address(value)
        print(f"{label:22} {address}")


# ---------------------------------------------------------------------------
# 3. Linux interface inspection
# ---------------------------------------------------------------------------

def inspect_interfaces() -> None:
    print_section("3. Network interfaces with ip")

    print(
        """
The modern Linux networking utility is ip, provided by the iproute2 suite.

Common read-only commands:

  ip link
      Show link-layer interfaces and their state.

  ip addr
      Show addresses assigned to interfaces.

  ip -br addr
      Show a compact human-readable address view.

  ip route
      Show the routing table.

  ip -s link
      Show interface statistics such as packet and byte counters.

The traditional ifconfig command is associated with net-tools and is not the
preferred modern interface-management command on current Linux systems.
"""
    )

    for command in (
        ["ip", "-br", "link"],
        ["ip", "-br", "addr"],
        ["ip", "addr", "show"],
        ["ip", "-s", "link"],
    ):
        if command_exists(command[0]):
            print_command(command)

    print_subsection("Interpreting an interface")

    print(
        """
Typical output may contain:

  lo
      Loopback interface. It permits processes on the same host to communicate
      through the networking stack without using a physical network.

  eth0 / enp... / ens...
      Possible Ethernet interface names.

  wlan0 / wlp...
      Possible Wi-Fi interface names.

  UP
      The interface is administratively enabled.

  LOWER_UP
      The underlying link is detected as operational.

  inet
      IPv4 address.

  inet6
      IPv6 address.

  scope global
      Generally usable beyond the local interface.

  scope host
      Restricted to the local host, as with 127.0.0.1 or ::1.
"""
    )


# ---------------------------------------------------------------------------
# 4. Parsing ip address output
# ---------------------------------------------------------------------------

@dataclass
class InterfaceAddress:
    interface: str
    family: str
    address: str
    prefix_length: int


def collect_interface_addresses() -> list[InterfaceAddress]:
    """
    Parse common `ip -j address` output.

    JSON output is preferable to fragile text parsing because the structure
    is machine-readable.
    """
    if not command_exists("ip"):
        return []

    code, stdout, _ = run_command(["ip", "-j", "address"])
    if code != 0 or not stdout.strip():
        return []

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []

    addresses: list[InterfaceAddress] = []

    for interface in data:
        name = interface.get("ifname", "?")

        for address_info in interface.get("addr_info", []):
            family = address_info.get("family", "")
            local = address_info.get("local")

            if not local:
                continue

            prefix_length = address_info.get("prefixlen", 0)

            addresses.append(
                InterfaceAddress(
                    interface=name,
                    family=family,
                    address=local,
                    prefix_length=prefix_length,
                )
            )

    return addresses


def demonstrate_structured_interface_data() -> None:
    print_section("4. Structured interface inspection")

    addresses = collect_interface_addresses()

    if not addresses:
        print("No structured interface data was available.")
        return

    for item in addresses:
        print(
            f"{item.interface:15} "
            f"{item.family:6} "
            f"{item.address}/{item.prefix_length}"
        )


# ---------------------------------------------------------------------------
# 5. DNS and name resolution
# ---------------------------------------------------------------------------

def demonstrate_dns() -> None:
    print_section("5. DNS configuration and name resolution")

    print(
        """
DNS configuration depends on the Linux distribution and network-management
stack. Common components include:

  /etc/resolv.conf
      A resolver configuration file. It may be a regular file or a symbolic
      link managed by another service.

  systemd-resolved
      A DNS resolver service used by many Linux installations.

  NetworkManager
      A network-management service that can configure DNS dynamically.

  resolvectl
      A command commonly used to inspect systemd-resolved state.

DNS server configuration and DNS resolution are separate concepts. A program
can resolve a name through the system resolver without directly implementing
the DNS protocol itself.

The following commands are inspection-oriented.
"""
    )

    if os.path.exists("/etc/resolv.conf"):
        print_subsection("/etc/resolv.conf")
        try:
            with open("/etc/resolv.conf", "r", encoding="utf-8") as file:
                for line in file:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        print(line)
        except OSError as exc:
            print(f"Could not read /etc/resolv.conf: {exc}")

    if command_exists("resolvectl"):
        print_subsection("resolvectl status")
        print_command(["resolvectl", "status"], timeout=5)

    if command_exists("nmcli"):
        print_subsection("NetworkManager DNS information")
        print_command(
            ["nmcli", "device", "show"],
            timeout=5,
        )

    print_subsection("Python system resolver")

    hostnames = [
        "localhost",
        "example.com",
        "invalid.invalid",
    ]

    for hostname in hostnames:
        try:
            addresses = socket.getaddrinfo(
                hostname,
                None,
                type=socket.SOCK_STREAM,
            )
            unique_addresses = sorted(
                {
                    item[4][0]
                    for item in addresses
                    if item[4]
                }
            )
            print(f"{hostname:20} -> {', '.join(unique_addresses)}")
        except socket.gaierror as exc:
            print(f"{hostname:20} -> resolution failed: {exc}")


# ---------------------------------------------------------------------------
# 6. DNS record inspection without external packages
# ---------------------------------------------------------------------------

def reverse_dns_demo() -> None:
    print_section("6. Forward and reverse DNS")

    print(
        """
Forward lookup:
    name -> IP address

Reverse lookup:
    IP address -> hostname

Reverse DNS is not guaranteed. An IP can have no PTR record, multiple
context-dependent names, or a name that does not correspond to the identity
you expect.

socket.gethostbyname() is convenient for basic IPv4 lookup. getaddrinfo()
is more general because it supports IPv4 and IPv6 and can resolve service
information as well.
"""
    )

    hostname = "localhost"

    try:
        print(f"gethostbyname({hostname!r}) -> {socket.gethostbyname(hostname)}")
    except socket.gaierror as exc:
        print(f"Lookup failed: {exc}")

    try:
        result = socket.getaddrinfo(
            hostname,
            "http",
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
        for item in result:
            family, socktype, protocol, canonname, sockaddr = item
            print(
                f"family={family} "
                f"socktype={socktype} "
                f"protocol={protocol} "
                f"address={sockaddr}"
            )
    except socket.gaierror as exc:
        print(f"getaddrinfo failed: {exc}")


# ---------------------------------------------------------------------------
# 7. Routing
# ---------------------------------------------------------------------------

def inspect_routes() -> None:
    print_section("7. Routing basics")

    print(
        """
A routing table answers a basic question:

    "Which interface and next hop should be used for this destination?"

A route commonly contains:

  destination prefix
  next-hop gateway, when required
  outgoing interface
  metric or preference
  route scope/type

Example conceptual table:

  192.168.1.0/24  dev eth0
  0.0.0.0/0       via 192.168.1.1 dev eth0

The /24 route handles destinations inside the local network.
The default route 0.0.0.0/0 handles destinations not matched by a more
specific route.

IPv6 uses ::/0 as the default route.

Linux performs longest-prefix matching: a more specific destination prefix
normally takes precedence over a less specific matching prefix.
"""
    )

    if not command_exists("ip"):
        print("ip command is unavailable.")
        return

    print_subsection("Routing table")
    print_command(["ip", "route"])

    print_subsection("IPv6 routing table")
    print_command(["ip", "-6", "route"])

    print_subsection("Route decision for a destination")

    destinations = ["127.0.0.1", "8.8.8.8", "1.1.1.1"]

    for destination in destinations:
        print_command(["ip", "route", "get", destination])


def demonstrate_longest_prefix_match() -> None:
    print_section("8. Longest-prefix matching simulation")

    routes = [
        ("0.0.0.0/0", "default-gateway"),
        ("10.0.0.0/8", "router-A"),
        ("10.20.0.0/16", "router-B"),
        ("10.20.30.0/24", "router-C"),
    ]

    parsed_routes = [
        (ipaddress.ip_network(prefix), next_hop)
        for prefix, next_hop in routes
    ]

    destinations = [
        "8.8.8.8",
        "10.5.1.2",
        "10.20.8.9",
        "10.20.30.99",
    ]

    for destination_text in destinations:
        destination = ipaddress.ip_address(destination_text)

        matching = [
            (network, next_hop)
            for network, next_hop in parsed_routes
            if destination in network
        ]

        selected_network, selected_next_hop = max(
            matching,
            key=lambda item: item[0].prefixlen,
        )

        print(
            f"{destination_text:15} -> "
            f"{selected_network} -> {selected_next_hop}"
        )


# ---------------------------------------------------------------------------
# 9. Connectivity with ping
# ---------------------------------------------------------------------------

def demonstrate_ping() -> None:
    print_section("9. Connectivity testing with ping")

    print(
        """
ping generally uses ICMP Echo Request and Echo Reply for IP connectivity
testing.

It can help answer:

  Can the destination be reached?
  Is there packet loss?
  What is the approximate round-trip time?

A successful ping does not prove that an application service is healthy.
A host can block ICMP while allowing TCP/HTTPS, or it can answer ICMP while
its web server is unavailable.

A single timeout can also be caused by congestion, filtering, routing issues,
or temporary loss.
"""
    )

    if not command_exists("ping"):
        print("ping command is unavailable.")
        return

    # -c is standard on Linux. Two packets keep the demonstration short.
    print_command(["ping", "-c", "2", "127.0.0.1"], timeout=5)

    print_subsection("Ping a public destination carefully")

    # This example is intentionally not executed automatically because
    # Internet connectivity and firewall policies vary.
    print("$ ping -c 4 example.com")
    print("Run this manually when external network testing is appropriate.")


# ---------------------------------------------------------------------------
# 10. Ports and sockets
# ---------------------------------------------------------------------------

def explain_ports() -> None:
    print_section("10. Ports and sockets")

    print(
        """
A TCP or UDP port is a 16-bit number:

    0 through 65535

The conventional ranges are:

    0-1023
        Well-known ports.

    1024-49151
        Registered ports.

    49152-65535
        Dynamic/private ports according to the commonly used IANA range.

A port is not globally unique. TCP port 8080 and UDP port 8080 are different
transport-layer endpoints.

A TCP connection is commonly identified by:

    protocol
    source IP
    source port
    destination IP
    destination port

A listening server usually binds to a local address and port, for example:

    0.0.0.0:8080

This means it is listening on port 8080 on all local IPv4 interfaces.

By contrast:

    127.0.0.1:8080

normally means the service is accessible only through the local loopback
interface.

This distinction is important for both functionality and security.
"""
    )

    common_ports = {
        22: "SSH",
        25: "SMTP",
        53: "DNS",
        80: "HTTP",
        123: "NTP",
        443: "HTTPS",
        3306: "MySQL",
        5432: "PostgreSQL",
        6379: "Redis",
        8080: "Common application development port",
    }

    for port, service in common_ports.items():
        print(f"{port:5}  {service}")


# ---------------------------------------------------------------------------
# 11. ss
# ---------------------------------------------------------------------------

def inspect_sockets_with_ss() -> None:
    print_section("11. Socket inspection with ss")

    print(
        """
ss is the modern Linux utility for inspecting sockets.

Useful examples:

    ss -t
        TCP sockets.

    ss -u
        UDP sockets.

    ss -l
        Listening sockets.

    ss -n
        Do not resolve names.

    ss -p
        Show process information when permitted.

    ss -tulpn
        Common compact view of TCP/UDP listening sockets with numeric
        addresses and process information.

Using -n is useful during troubleshooting because DNS lookups can make
output slower or confusing.
"""
    )

    if not command_exists("ss"):
        print("ss is unavailable.")
        return

    commands = [
        ["ss", "-tuln"],
        ["ss", "-s"],
    ]

    for command in commands:
        print_command(command)

    print_subsection("Listening sockets with processes")

    # Process information can require elevated privileges for some sockets.
    print_command(["ss", "-tulpn"])


# ---------------------------------------------------------------------------
# 12. netstat
# ---------------------------------------------------------------------------

def inspect_with_netstat() -> None:
    print_section("12. netstat and its relationship to ss")

    print(
        """
netstat is part of the older net-tools collection. It remains useful on
systems where it is installed, but ss is generally preferred on modern Linux.

Comparable examples:

    netstat -tuln
    ss -tuln

    netstat -rn
    ip route

    netstat -i
    ip -s link

The exact output formats differ, so scripts should not assume that netstat
and ss produce identical columns.

A practical troubleshooting habit is to learn ss first while recognizing
netstat because legacy documentation and older systems still use it.
"""
    )

    if not command_exists("netstat"):
        print("netstat is not installed on this system.")
        print("The command belongs to the net-tools package on many distributions.")
        return

    print_command(["netstat", "-tuln"])
    print_command(["netstat", "-rn"])


# ---------------------------------------------------------------------------
# 13. Local TCP server and client
# ---------------------------------------------------------------------------

class LocalTcpServer:
    """
    A small TCP server used to demonstrate:
      - a listening port
      - localhost binding
      - accept()
      - recv()
      - sendall()
      - context-managed sockets
      - clean shutdown
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.requested_port = port
        self.socket: Optional[socket.socket] = None
        self.port: Optional[int] = None

    def start(self) -> None:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # SO_REUSEADDR helps development servers restart without waiting
        # unnecessarily for old socket state.
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Port 0 asks the OS to select an unused ephemeral port.
        server_socket.bind((self.host, self.requested_port))
        server_socket.listen(1)
        server_socket.settimeout(5)

        self.socket = server_socket
        self.port = server_socket.getsockname()[1]

    def serve_once(self) -> None:
        if self.socket is None or self.port is None:
            raise RuntimeError("Server has not been started.")

        try:
            connection, address = self.socket.accept()
        except socket.timeout:
            print("No client connected before timeout.")
            return

        with connection:
            print(f"Accepted connection from {address}")
            data = connection.recv(4096)

            if not data:
                return

            print(f"Server received: {data.decode(errors='replace')!r}")
            connection.sendall(b"ACK:" + data)

    def close(self) -> None:
        if self.socket is not None:
            self.socket.close()
            self.socket = None


def demonstrate_tcp_server() -> None:
    print_section("13. Practical TCP socket demonstration")

    server = LocalTcpServer()

    try:
        server.start()

        print(
            f"Server listening on {server.host}:{server.port}. "
            "This is a local-only demonstration."
        )

        # The client runs in the same process. A short-lived background
        # thread is sufficient for this educational demonstration.
        import threading

        server_thread = threading.Thread(
            target=server.serve_once,
            daemon=True,
        )
        server_thread.start()

        time.sleep(0.1)

        with socket.create_connection(
            (server.host, server.port),
            timeout=3,
        ) as client:
            message = b"hello-linux-networking"
            client.sendall(message)
            response = client.recv(4096)
            print(f"Client received: {response.decode(errors='replace')!r}")

        server_thread.join(timeout=2)

        if command_exists("ss"):
            print_subsection("Inspect the socket while a server is listening")

            # The socket closes quickly after the one request, so ss may show
            # no listener by the time it runs. The command is still useful
            # as the standard inspection technique.
            print_command(["ss", "-tnl"])

    except OSError as exc:
        print(f"TCP demonstration failed: {exc}")
    finally:
        server.close()


# ---------------------------------------------------------------------------
# 14. UDP demonstration
# ---------------------------------------------------------------------------

def demonstrate_udp() -> None:
    print_section("14. UDP socket demonstration")

    print(
        """
UDP is connectionless at the transport protocol level. Applications send
datagrams rather than establishing a TCP byte-stream connection.

Important trade-offs:

  TCP:
      reliable ordered byte stream, connection-oriented, retransmission and
      congestion-control mechanisms.

  UDP:
      message-oriented datagrams, lower protocol overhead, no TCP-style
      delivery guarantee or ordering.

DNS commonly uses UDP for ordinary queries, although DNS can also use TCP
and modern DNS transports can use other protocols.
"""
    )

    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        server.bind(("127.0.0.1", 0))
        server.settimeout(3)
        port = server.getsockname()[1]

        print(f"UDP server bound to 127.0.0.1:{port}")

        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            client.sendto(
                b"udp-message",
                ("127.0.0.1", port),
            )

            data, address = server.recvfrom(4096)
            print(f"Received {data!r} from {address}")
        finally:
            client.close()

    except OSError as exc:
        print(f"UDP demonstration failed: {exc}")
    finally:
        server.close()


# ---------------------------------------------------------------------------
# 15. DNS and ports through getaddrinfo
# ---------------------------------------------------------------------------

def demonstrate_service_resolution() -> None:
    print_section("15. Resolving host and service information")

    examples = [
        ("localhost", "http"),
        ("localhost", "ssh"),
        ("localhost", "domain"),
    ]

    for host, service in examples:
        try:
            results = socket.getaddrinfo(
                host,
                service,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )

            print(f"\n{host}:{service}")

            for family, socktype, protocol, canonical, sockaddr in results:
                print(
                    f"  family={family} "
                    f"socket_type={socktype} "
                    f"protocol={protocol} "
                    f"address={sockaddr}"
                )
        except socket.gaierror as exc:
            print(f"{host}:{service} -> {exc}")


# ---------------------------------------------------------------------------
# 16. Network interface selection
# ---------------------------------------------------------------------------

def determine_local_address_for_destination() -> None:
    print_section("16. Determining the local address used for a destination")

    print(
        """
A useful diagnostic technique is to create a UDP socket and ask the operating
system which local address it would use when communicating with a destination.
No application payload needs to be transmitted for this technique.

This is different from simply asking for the machine's hostname because a
machine can have several active interfaces and addresses.
"""
    )

    destinations = [
        ("8.8.8.8", 53),
        ("127.0.0.1", 53),
    ]

    for destination, port in destinations:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        try:
            sock.connect((destination, port))
            local_address = sock.getsockname()[0]
            print(
                f"Destination {destination}:{port} "
                f"would use local address {local_address}"
            )
        except OSError as exc:
            print(f"Could not determine route to {destination}: {exc}")
        finally:
            sock.close()


# ---------------------------------------------------------------------------
# 17. Validation and edge cases
# ---------------------------------------------------------------------------

def demonstrate_validation() -> None:
    print_section("17. Address, port, and hostname validation")

    address_examples = [
        "192.168.1.1",
        "192.168.1.999",
        "2001:db8::1",
        "2001:::1",
        "127.0.0.1/8",
    ]

    for value in address_examples:
        try:
            if "/" in value:
                parsed = ipaddress.ip_interface(value)
            else:
                parsed = ipaddress.ip_address(value)
            print(f"{value:20} valid -> {parsed}")
        except ValueError as exc:
            print(f"{value:20} invalid -> {exc}")

    port_examples = [-1, 0, 22, 443, 65535, 65536]

    for port in port_examples:
        valid = 0 <= port <= 65535
        print(f"Port {port:6}: {'valid' if valid else 'invalid'}")

    hostname_examples = [
        "example.com",
        "localhost",
        "invalid.invalid",
    ]

    hostname_pattern = re.compile(
        r"^(?=.{1,253}\.?$)"
        r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
        r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
    )

    for hostname in hostname_examples:
        print(
            f"{hostname:20} "
            f"syntactically valid={bool(hostname_pattern.match(hostname))}"
        )


# ---------------------------------------------------------------------------
# 18. A small troubleshooting workflow
# ---------------------------------------------------------------------------

def troubleshooting_workflow() -> None:
    print_section("18. Practical Linux networking troubleshooting workflow")

    print(
        """
When a service cannot be reached, isolate the problem from the bottom upward.

1. Inspect interfaces:
       ip -br link
       ip -br addr

2. Inspect the routing decision:
       ip route
       ip route get <destination>

3. Test basic IP connectivity:
       ping <destination>

4. Test DNS independently:
       getent hosts <hostname>
       resolvectl query <hostname>

5. Inspect listening services:
       ss -tuln
       ss -tulpn

6. Test the application port:
       nc -vz <host> <port>
       curl -v http://<host>:<port>

7. Inspect firewalls and security controls when appropriate.

The order matters because a DNS problem and a TCP listening problem produce
different symptoms. A successful ping does not establish that TCP port 443 is
open, and an open TCP port does not prove that an HTTP application is healthy.
"""
    )


# ---------------------------------------------------------------------------
# 19. Common mistakes
# ---------------------------------------------------------------------------

def common_mistakes() -> None:
    print_section("19. Common mistakes and subtle behaviors")

    mistakes = [
        (
            "Confusing interface state with Internet access",
            "An UP interface can exist without a usable route, gateway, DNS, or upstream connectivity.",
        ),
        (
            "Assuming ping proves a service works",
            "ICMP reachability and application-layer availability are separate tests.",
        ),
        (
            "Using 0.0.0.0 as a remote destination",
            "0.0.0.0 is commonly a wildcard/local binding address, not a normal remote host address.",
        ),
        (
            "Ignoring IPv6",
            "A host may resolve an AAAA record and attempt IPv6 even when IPv4 troubleshooting appears correct.",
        ),
        (
            "Using hostname resolution during socket inspection",
            "ss without -n may perform name/service resolution and make output harder to interpret.",
        ),
        (
            "Assuming port numbers identify services",
            "A port number is only an endpoint identifier. A service can listen on a non-standard port.",
        ),
        (
            "Assuming localhost means the whole network",
            "Binding to 127.0.0.1 normally restricts access to the local host.",
        ),
        (
            "Parsing ip output as plain text unnecessarily",
            "ip -j can provide structured JSON that is more robust for automation.",
        ),
        (
            "Assuming netstat is always installed",
            "Modern distributions may provide iproute2 and omit net-tools.",
        ),
    ]

    for mistake, explanation in mistakes:
        print(f"\n{mistake}")
        print(f"  {explanation}")


# ---------------------------------------------------------------------------
# 20. Performance and production considerations
# ---------------------------------------------------------------------------

def production_considerations() -> None:
    print_section("20. Performance, security, and production considerations")

    print(
        """
Performance:

  * Avoid unnecessary DNS lookups in monitoring loops.
  * Prefer numeric output such as ss -n when name resolution is unnecessary.
  * Reuse connections where the application protocol supports it.
  * Use appropriate socket timeouts.
  * Avoid creating unbounded threads or processes per network request.
  * Measure latency, throughput, packet loss, connection counts, and error
    rates rather than relying on a single metric.

Reliability:

  * Treat DNS failures separately from TCP failures.
  * Use explicit timeouts.
  * Retry selectively rather than retrying every failure indefinitely.
  * Respect IPv4/IPv6 behavior and dual-stack environments.
  * Log the destination, error category, and timing needed for diagnosis.

Security:

  * Bind services to the smallest required address scope.
  * Do not expose administrative services unnecessarily.
  * Use encryption for sensitive application traffic.
  * Validate untrusted hostnames, IP addresses, ports, and application data.
  * Apply firewall rules according to the actual trust boundary.
  * Avoid embedding credentials or secrets in diagnostic scripts.
  * Be careful with commands that modify routes, addresses, firewall rules,
    or interfaces.

Operational diagnosis:

  A useful model is:

      Interface
          ->
      IP configuration
          ->
      Route
          ->
      DNS
          ->
      Transport port
          ->
      Application protocol
          ->
      Application behavior

  Each layer can fail independently.
"""
    )


# ---------------------------------------------------------------------------
# 21. Safe command reference
# ---------------------------------------------------------------------------

def command_reference() -> None:
    print_section("21. Linux networking command reference")

    commands = [
        ("ip -br link", "Compact interface/link status"),
        ("ip -br addr", "Compact IP address view"),
        ("ip addr", "Detailed interface addresses"),
        ("ip -s link", "Interface statistics"),
        ("ip route", "IPv4 routing table"),
        ("ip -6 route", "IPv6 routing table"),
        ("ip route get 8.8.8.8", "Show route selected for destination"),
        ("ping -c 4 example.com", "ICMP reachability test"),
        ("ss -tuln", "Listening TCP/UDP sockets"),
        ("ss -tulpn", "Listening sockets with process information"),
        ("ss -s", "Socket summary"),
        ("netstat -tuln", "Legacy socket inspection"),
        ("netstat -rn", "Legacy routing-table view"),
        ("getent hosts example.com", "Use system name-service lookup"),
        ("resolvectl status", "Inspect systemd-resolved state"),
        ("resolvectl query example.com", "Query DNS through systemd-resolved"),
    ]

    width = max(len(command) for command, _ in commands)

    for command, purpose in commands:
        print(f"{command:<{width}}  {purpose}")


# ---------------------------------------------------------------------------
# 22. Demonstration of routing decision in Python
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Route:
    network: ipaddress.IPv4Network
    interface: str
    gateway: Optional[str] = None
    metric: int = 100


class RoutingTable:
    """A small educational routing-table model."""

    def __init__(self, routes: Iterable[Route]):
        self.routes = list(routes)

    def lookup(self, destination: str) -> Optional[Route]:
        address = ipaddress.ip_address(destination)

        matches = [
            route
            for route in self.routes
            if address in route.network
        ]

        if not matches:
            return None

        # Longest prefix first. Metric is used as a secondary tie-breaker.
        return min(
            matches,
            key=lambda route: (-route.network.prefixlen, route.metric),
        )


def demonstrate_routing_model() -> None:
    print_section("22. Educational routing-table implementation")

    table = RoutingTable(
        [
            Route(
                ipaddress.ip_network("0.0.0.0/0"),
                interface="eth0",
                gateway="192.168.1.1",
                metric=100,
            ),
            Route(
                ipaddress.ip_network("10.0.0.0/8"),
                interface="vpn0",
                gateway=None,
                metric=100,
            ),
            Route(
                ipaddress.ip_network("10.10.0.0/16"),
                interface="vpn1",
                gateway=None,
                metric=50,
            ),
            Route(
                ipaddress.ip_network("10.10.20.0/24"),
                interface="vpn2",
                gateway=None,
                metric=10,
            ),
        ]
    )

    for destination in [
        "8.8.8.8",
        "10.5.1.1",
        "10.10.4.2",
        "10.10.20.50",
    ]:
        route = table.lookup(destination)

        if route is None:
            print(f"{destination:15} -> no route")
        else:
            gateway = route.gateway or "direct"
            print(
                f"{destination:15} -> "
                f"{route.network} via {gateway} "
                f"dev {route.interface} metric {route.metric}"
            )


# ---------------------------------------------------------------------------
# 23. Testing helpers
# ---------------------------------------------------------------------------

def run_self_tests() -> None:
    print_section("23. Self-tests")

    assert ipaddress.ip_address("127.0.0.1").is_loopback
    assert ipaddress.ip_address("192.168.1.10").is_private
    assert ipaddress.ip_address("8.8.8.8") not in ipaddress.ip_network(
        "192.168.1.0/24"
    )

    table = RoutingTable(
        [
            Route(ipaddress.ip_network("0.0.0.0/0"), "eth0"),
            Route(ipaddress.ip_network("10.0.0.0/8"), "vpn0"),
            Route(ipaddress.ip_network("10.1.0.0/16"), "vpn1"),
        ]
    )

    assert table.lookup("8.8.8.8").interface == "eth0"
    assert table.lookup("10.20.1.1").interface == "vpn0"
    assert table.lookup("10.1.2.3").interface == "vpn1"

    try:
        ipaddress.ip_address("999.999.999.999")
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid IPv4 address was accepted.")

    assert 0 <= 0 <= 65535
    assert 0 <= 65535 <= 65535
    assert not (0 <= 65536 <= 65535)

    print("All self-tests passed.")


# ---------------------------------------------------------------------------
# 24. Main program
# ---------------------------------------------------------------------------

def main() -> None:
    print("Linux Networking Study and Demonstration Program")
    print(f"Platform: {platform.platform()}")
    print(f"Python: {platform.python_version()}")
    print(f"Effective user ID: {os.geteuid() if hasattr(os, 'geteuid') else 'N/A'}")

    explain_fundamentals()
    demonstrate_ip_addresses()
    inspect_interfaces()
    demonstrate_structured_interface_data()
    demonstrate_dns()
    reverse_dns_demo()
    inspect_routes()
    demonstrate_longest_prefix_match()
    demonstrate_ping()
    explain_ports()
    inspect_sockets_with_ss()
    inspect_with_netstat()
    demonstrate_tcp_server()
    demonstrate_udp()
    demonstrate_service_resolution()
    determine_local_address_for_destination()
    demonstrate_validation()
    troubleshooting_workflow()
    common_mistakes()
    production_considerations()
    command_reference()
    demonstrate_routing_model()
    run_self_tests()

    print_section("End of study program")
    print(
        "The demonstrations intentionally avoid changing system networking "
        "configuration."
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(130)
