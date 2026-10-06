#!/usr/bin/env python3
"""
Network Virtualization Laboratory

A self-contained simulation of:
- Virtual switches
- Virtual networks and VLAN-like segmentation
- Overlay networks and VXLAN-style VNIs
- Software-defined networking concepts
- Flow tables and forwarding decisions
- Control plane versus data plane
- Virtual network interfaces
- Network namespaces as a conceptual model
- Security policy enforcement
- Routing between virtual networks
- Encapsulation and decapsulation
- Failure detection and operational diagnostics

This is a simulation. It does not create real network interfaces or modify the
host operating system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import ipaddress
import random
import time
from typing import Dict, List, Optional, Tuple


class PacketAction(Enum):
    FORWARD = "FORWARD"
    DROP = "DROP"
    FLOOD = "FLOOD"
    ROUTE = "ROUTE"


class PortType(Enum):
    HOST = "HOST"
    UPLINK = "UPLINK"
    PATCH = "PATCH"


@dataclass(frozen=True)
class MACAddress:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.lower()
        parts = normalized.split(":")
        if len(parts) != 6:
            raise ValueError(f"Invalid MAC address: {self.value}")
        if any(len(part) != 2 for part in parts):
            raise ValueError(f"Invalid MAC address: {self.value}")
        if any(c not in "0123456789abcdef" for part in parts for c in part):
            raise ValueError(f"Invalid MAC address: {self.value}")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass
class VirtualNIC:
    name: str
    mac: MACAddress
    ip: ipaddress.IPv4Interface
    network_name: str
    host_name: str

    def __str__(self) -> str:
        return f"{self.host_name}/{self.name} {self.mac} {self.ip}"


@dataclass
class Packet:
    source_mac: MACAddress
    destination_mac: MACAddress
    source_ip: Optional[ipaddress.IPv4Address]
    destination_ip: Optional[ipaddress.IPv4Address]
    payload: str
    vlan_id: Optional[int] = None
    vni: Optional[int] = None
    ttl: int = 64

    def summary(self) -> str:
        return (
            f"{self.source_mac} -> {self.destination_mac}, "
            f"{self.source_ip} -> {self.destination_ip}, "
            f"VLAN={self.vlan_id}, VNI={self.vni}, TTL={self.ttl}"
        )


@dataclass
class VirtualPort:
    name: str
    port_type: PortType
    attached_nic: Optional[VirtualNIC] = None
    enabled: bool = True


@dataclass
class FlowEntry:
    destination_mac: MACAddress
    output_port: str
    vlan_id: Optional[int] = None
    packet_count: int = 0
    byte_count: int = 0


@dataclass
class VirtualNetwork:
    name: str
    subnet: ipaddress.IPv4Network
    vlan_id: Optional[int] = None
    vni: Optional[int] = None
    gateway: Optional[ipaddress.IPv4Address] = None
    isolated: bool = False

    def contains(self, address: ipaddress.IPv4Address) -> bool:
        return address in self.subnet


@dataclass
class OverlayPacket:
    outer_source: str
    outer_destination: str
    vni: int
    inner_packet: Packet

    def describe(self) -> str:
        return (
            f"VXLAN-like encapsulation: outer {self.outer_source} -> "
            f"{self.outer_destination}, VNI={self.vni}; "
            f"inner [{self.inner_packet.summary()}]"
        )


@dataclass
class Host:
    name: str
    management_ip: ipaddress.IPv4Address
    nics: Dict[str, VirtualNIC] = field(default_factory=dict)

    def add_nic(self, nic: VirtualNIC) -> None:
        if nic.name in self.nics:
            raise ValueError(f"NIC {nic.name} already exists on {self.name}")
        self.nics[nic.name] = nic


class VirtualSwitch:
    """
    A simplified Ethernet virtual switch.

    The switch learns source MAC addresses and stores them in a forwarding
    table. Unknown destinations are flooded to eligible ports, which mirrors
    the fundamental behavior of Ethernet switching.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.ports: Dict[str, VirtualPort] = {}
        self.mac_table: Dict[MACAddress, str] = {}
        self.flow_entries: Dict[Tuple[MACAddress, Optional[int]], FlowEntry] = {}
        self.packet_drops = 0
        self.packet_forwards = 0

    def add_port(self, port: VirtualPort) -> None:
        if port.name in self.ports:
            raise ValueError(f"Port {port.name} already exists")
        self.ports[port.name] = port

    def learn_source(self, packet: Packet, ingress_port: str) -> None:
        if ingress_port not in self.ports:
            raise ValueError(f"Unknown ingress port: {ingress_port}")

        self.mac_table[packet.source_mac] = ingress_port
        key = (packet.source_mac, packet.vlan_id)

        existing = self.flow_entries.get(key)
        if existing is None:
            self.flow_entries[key] = FlowEntry(
                destination_mac=packet.source_mac,
                output_port=ingress_port,
                vlan_id=packet.vlan_id,
            )
        else:
            existing.output_port = ingress_port

    def lookup(self, packet: Packet) -> Optional[str]:
        return self.mac_table.get(packet.destination_mac)

    def receive(self, packet: Packet, ingress_port: str) -> List[str]:
        """
        Decide where an Ethernet frame should go.

        A disabled port cannot inject traffic. A known destination is unicast.
        An unknown destination is flooded except back toward the ingress port.
        """
        port = self.ports.get(ingress_port)

        if port is None or not port.enabled:
            self.packet_drops += 1
            return []

        self.learn_source(packet, ingress_port)

        destination_port = self.lookup(packet)

        if destination_port is not None:
            if destination_port == ingress_port:
                return []

            entry = self.flow_entries[(packet.destination_mac, packet.vlan_id)]
            entry.packet_count += 1
            entry.byte_count += len(packet.payload.encode("utf-8"))
            self.packet_forwards += 1
            return [destination_port]

        eligible = [
            name
            for name, candidate in self.ports.items()
            if candidate.enabled and name != ingress_port
        ]

        self.packet_forwards += len(eligible)
        return eligible

    def show_mac_table(self) -> None:
        print(f"\n[{self.name}] MAC forwarding table")
        if not self.mac_table:
            print("  <empty>")
            return

        for mac, port in sorted(
            self.mac_table.items(), key=lambda item: str(item[0])
        ):
            print(f"  {mac} -> {port}")


class SDNController:
    """
    A minimal SDN control plane.

    The controller does not forward packets itself. It computes policy and
    installs forwarding decisions into virtual switches, demonstrating the
    separation between control-plane intent and data-plane forwarding.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.switches: Dict[str, VirtualSwitch] = {}
        self.networks: Dict[str, VirtualNetwork] = {}
        self.policies: List[Tuple[str, str, str]] = []

    def register_switch(self, switch: VirtualSwitch) -> None:
        self.switches[switch.name] = switch

    def register_network(self, network: VirtualNetwork) -> None:
        if network.name in self.networks:
            raise ValueError(f"Network {network.name} already exists")
        self.networks[network.name] = network

    def add_policy(self, source_network: str, destination_network: str, action: str) -> None:
        if source_network not in self.networks:
            raise ValueError(f"Unknown source network: {source_network}")
        if destination_network not in self.networks:
            raise ValueError(f"Unknown destination network: {destination_network}")

        allowed_actions = {"ALLOW", "DENY"}
        if action not in allowed_actions:
            raise ValueError(f"Unsupported action: {action}")

        self.policies.append((source_network, destination_network, action))

    def policy_for(self, source: str, destination: str) -> str:
        for source_network, destination_network, action in reversed(self.policies):
            if source_network == source and destination_network == destination:
                return action

        return "DENY"

    def program_switch(self, switch_name: str) -> None:
        switch = self.switches[switch_name]

        print(f"\nController {self.name} programming {switch.name}")

        for mac, port in switch.mac_table.items():
            key = (mac, None)
            switch.flow_entries[key] = FlowEntry(
                destination_mac=mac,
                output_port=port,
            )

        print(
            f"  Programmed {len(switch.flow_entries)} forwarding entries "
            "from current topology state."
        )


class VirtualRouter:
    """
    Provides a simplified Layer-3 boundary between virtual networks.

    The router performs the conceptual functions of routing:
    determine the destination virtual network, enforce policy, decrement TTL,
    and forward toward the destination NIC.
    """

    def __init__(self, name: str, controller: SDNController) -> None:
        self.name = name
        self.controller = controller
        self.routes: Dict[str, str] = {}

    def add_route(self, destination_network: str, next_hop_network: str) -> None:
        if destination_network not in self.controller.networks:
            raise ValueError("Destination network is not registered")
        if next_hop_network not in self.controller.networks:
            raise ValueError("Next-hop network is not registered")
        self.routes[destination_network] = next_hop_network

    def network_for_ip(self, address: ipaddress.IPv4Address) -> Optional[str]:
        matches = [
            network
            for network in self.controller.networks.values()
            if network.contains(address)
        ]

        if not matches:
            return None

        # Longest-prefix matching is represented by selecting the most specific
        # subnet if overlapping networks exist.
        matches.sort(key=lambda n: n.subnet.prefixlen, reverse=True)
        return matches[0].name

    def route(self, packet: Packet, source_network: str) -> bool:
        if packet.destination_ip is None:
            return False

        if packet.ttl <= 1:
            print("  Router dropped packet because TTL expired.")
            return False

        destination_network = self.network_for_ip(packet.destination_ip)

        if destination_network is None:
            print("  Router dropped packet because destination is unroutable.")
            return False

        policy = self.controller.policy_for(source_network, destination_network)

        if policy != "ALLOW":
            print(
                f"  Router denied {source_network} -> "
                f"{destination_network} according to SDN policy."
            )
            return False

        packet.ttl -= 1
        print(
            f"  Router {self.name} routed {source_network} -> "
            f"{destination_network}; new TTL={packet.ttl}"
        )
        return True


class OverlayNetwork:
    """
    Models the logical behavior of an overlay network.

    VXLAN encapsulates an inner Ethernet frame inside an outer transport packet
    and uses a VNI to identify the logical Layer-2 segment.
    """

    def __init__(self, name: str, vni: int) -> None:
        if not 1 <= vni <= 16_777_215:
            raise ValueError("VXLAN VNI must fit in 24 bits")
        self.name = name
        self.vni = vni
        self.endpoint_locations: Dict[MACAddress, str] = {}

    def register_endpoint(self, mac: MACAddress, tunnel_endpoint: str) -> None:
        self.endpoint_locations[mac] = tunnel_endpoint

    def encapsulate(
        self,
        packet: Packet,
        outer_source: str,
        outer_destination: str,
    ) -> OverlayPacket:
        packet.vni = self.vni
        return OverlayPacket(
            outer_source=outer_source,
            outer_destination=outer_destination,
            vni=self.vni,
            inner_packet=packet,
        )

    def decapsulate(self, overlay_packet: OverlayPacket) -> Packet:
        if overlay_packet.vni != self.vni:
            raise ValueError(
                f"VNI mismatch: received {overlay_packet.vni}, "
                f"expected {self.vni}"
            )

        overlay_packet.inner_packet.vni = None
        return overlay_packet.inner_packet


class NetworkLab:
    """
    Builds and exercises a small virtual data-center topology.
    """

    def __init__(self) -> None:
        self.controller = SDNController("sdn-controller")
        self.router = VirtualRouter("virtual-router-01", self.controller)
        self.overlay = OverlayNetwork("tenant-overlay", 5001)

        self.hosts: Dict[str, Host] = {}
        self.switches: Dict[str, VirtualSwitch] = {}

    def build(self) -> None:
        frontend = VirtualNetwork(
            name="frontend",
            subnet=ipaddress.ip_network("10.10.10.0/24"),
            vlan_id=110,
            vni=5001,
            gateway=ipaddress.ip_address("10.10.10.1"),
        )

        backend = VirtualNetwork(
            name="backend",
            subnet=ipaddress.ip_network("10.10.20.0/24"),
            vlan_id=120,
            vni=5002,
            gateway=ipaddress.ip_address("10.10.20.1"),
        )

        database = VirtualNetwork(
            name="database",
            subnet=ipaddress.ip_network("10.10.30.0/24"),
            vlan_id=130,
            vni=5003,
            gateway=ipaddress.ip_address("10.10.30.1"),
            isolated=True,
        )

        for network in (frontend, backend, database):
            self.controller.register_network(network)

        # The policy is intentionally asymmetric: frontend can reach backend,
        # backend can reach database, but frontend cannot directly reach DB.
        self.controller.add_policy("frontend", "frontend", "ALLOW")
        self.controller.add_policy("backend", "backend", "ALLOW")
        self.controller.add_policy("database", "database", "ALLOW")
        self.controller.add_policy("frontend", "backend", "ALLOW")
        self.controller.add_policy("backend", "frontend", "ALLOW")
        self.controller.add_policy("backend", "database", "ALLOW")
        self.controller.add_policy("database", "backend", "ALLOW")
        self.controller.add_policy("frontend", "database", "DENY")
        self.controller.add_policy("database", "frontend", "DENY")

        self.router.add_route("frontend", "frontend")
        self.router.add_route("backend", "backend")
        self.router.add_route("database", "database")

        switch_a = VirtualSwitch("vswitch-a")
        switch_b = VirtualSwitch("vswitch-b")

        self.switches[switch_a.name] = switch_a
        self.switches[switch_b.name] = switch_b

        self.controller.register_switch(switch_a)
        self.controller.register_switch(switch_b)

        frontend_host = Host(
            "web-01",
            ipaddress.ip_address("192.0.2.11"),
        )
        backend_host = Host(
            "app-01",
            ipaddress.ip_address("192.0.2.12"),
        )
        database_host = Host(
            "db-01",
            ipaddress.ip_address("192.0.2.13"),
        )

        web_nic = VirtualNIC(
            name="eth0",
            mac=MACAddress("02:00:00:00:10:01"),
            ip=ipaddress.ip_interface("10.10.10.10/24"),
            network_name="frontend",
            host_name="web-01",
        )

        app_nic = VirtualNIC(
            name="eth0",
            mac=MACAddress("02:00:00:00:20:01"),
            ip=ipaddress.ip_interface("10.10.20.10/24"),
            network_name="backend",
            host_name="app-01",
        )

        db_nic = VirtualNIC(
            name="eth0",
            mac=MACAddress("02:00:00:00:30:01"),
            ip=ipaddress.ip_interface("10.10.30.10/24"),
            network_name="database",
            host_name="db-01",
        )

        frontend_host.add_nic(web_nic)
        backend_host.add_nic(app_nic)
        database_host.add_nic(db_nic)

        self.hosts = {
            frontend_host.name: frontend_host,
            backend_host.name: backend_host,
            database_host.name: database_host,
        }

        switch_a.add_port(
            VirtualPort(
                "web-port",
                PortType.HOST,
                web_nic,
            )
        )
        switch_a.add_port(
            VirtualPort(
                "app-port",
                PortType.HOST,
                app_nic,
            )
        )
        switch_a.add_port(
            VirtualPort(
                "vxlan-uplink",
                PortType.UPLINK,
            )
        )

        switch_b.add_port(
            VirtualPort(
                "db-port",
                PortType.HOST,
                db_nic,
            )
        )
        switch_b.add_port(
            VirtualPort(
                "vxlan-uplink",
                PortType.UPLINK,
            )
        )

        self.overlay.register_endpoint(web_nic.mac, "10.0.0.11")
        self.overlay.register_endpoint(app_nic.mac, "10.0.0.12")
        self.overlay.register_endpoint(db_nic.mac, "10.0.0.13")

    def send_same_network_frame(self) -> None:
        print("\n=== Virtual-switch forwarding ===")

        web = self.hosts["web-01"].nics["eth0"]
        app = self.hosts["app-01"].nics["eth0"]

        packet = Packet(
            source_mac=web.mac,
            destination_mac=app.mac,
            source_ip=web.ip.ip,
            destination_ip=app.ip.ip,
            payload="GET /api/orders",
            vlan_id=110,
        )

        switch = self.switches["vswitch-a"]

        print(f"Incoming frame: {packet.summary()}")

        # The first packet is unknown to the switch and therefore floods.
        outputs = switch.receive(packet, "web-port")
        print(f"First forwarding decision: {outputs}")

        # The return packet teaches the switch the destination location.
        reply = Packet(
            source_mac=app.mac,
            destination_mac=web.mac,
            source_ip=app.ip.ip,
            destination_ip=web.ip.ip,
            payload="HTTP 200",
            vlan_id=110,
        )

        outputs = switch.receive(reply, "app-port")
        print(f"Reply forwarding decision: {outputs}")

        switch.show_mac_table()

    def send_routed_packet(self) -> None:
        print("\n=== Layer-3 virtual-network routing ===")

        web = self.hosts["web-01"].nics["eth0"]
        app = self.hosts["app-01"].nics["eth0"]

        packet = Packet(
            source_mac=web.mac,
            destination_mac=MACAddress("02:00:00:00:20:01"),
            source_ip=web.ip.ip,
            destination_ip=app.ip.ip,
            payload="POST /internal/order",
            vlan_id=110,
        )

        allowed = self.router.route(packet, "frontend")

        if allowed:
            packet.vlan_id = 120
            print(
                f"  Routed packet enters backend segment with "
                f"destination {packet.destination_ip}."
            )

    def demonstrate_overlay(self) -> None:
        print("\n=== Overlay encapsulation ===")

        web = self.hosts["web-01"].nics["eth0"]
        app = self.hosts["app-01"].nics["eth0"]

        inner = Packet(
            source_mac=web.mac,
            destination_mac=app.mac,
            source_ip=web.ip.ip,
            destination_ip=app.ip.ip,
            payload="overlay application traffic",
        )

        outer = self.overlay.encapsulate(
            inner,
            outer_source="10.0.0.11",
            outer_destination="10.0.0.12",
        )

        print(outer.describe())

        recovered = self.overlay.decapsulate(outer)
        print(f"After decapsulation: {recovered.summary()}")

    def demonstrate_policy_denial(self) -> None:
        print("\n=== SDN policy enforcement ===")

        web = self.hosts["web-01"].nics["eth0"]
        db = self.hosts["db-01"].nics["eth0"]

        packet = Packet(
            source_mac=web.mac,
            destination_mac=db.mac,
            source_ip=web.ip.ip,
            destination_ip=db.ip.ip,
            payload="direct database connection",
        )

        allowed = self.router.route(packet, "frontend")

        print(f"Direct frontend -> database result: {'allowed' if allowed else 'blocked'}")

    def demonstrate_port_failure(self) -> None:
        print("\n=== Virtual-port failure ===")

        switch = self.switches["vswitch-a"]
        switch.ports["app-port"].enabled = False

        web = self.hosts["web-01"].nics["eth0"]
        app = self.hosts["app-01"].nics["eth0"]

        packet = Packet(
            source_mac=web.mac,
            destination_mac=app.mac,
            source_ip=web.ip.ip,
            destination_ip=app.ip.ip,
            payload="traffic during failure",
            vlan_id=110,
        )

        outputs = switch.receive(packet, "web-port")

        print(f"Forwarding result after app-port failure: {outputs}")
        print(f"Switch drop counter: {switch.packet_drops}")

        # Restore the port so subsequent demonstrations would not inherit the
        # artificial failure.
        switch.ports["app-port"].enabled = True

    def show_topology(self) -> None:
        print("\n=== Virtual topology ===")

        for network in self.controller.networks.values():
            print(
                f"Network={network.name:<10} "
                f"Subnet={network.subnet} "
                f"VLAN={network.vlan_id} "
                f"VNI={network.vni} "
                f"Gateway={network.gateway} "
                f"Isolated={network.isolated}"
            )

        print("\nHosts:")
        for host in self.hosts.values():
            print(f"  {host.name}:")
            for nic in host.nics.values():
                print(f"    {nic}")

        print("\nVirtual switches:")
        for switch in self.switches.values():
            print(f"  {switch.name}: {list(switch.ports)}")

    def run(self) -> None:
        self.show_topology()
        self.send_same_network_frame()
        self.send_routed_packet()
        self.demonstrate_overlay()
        self.demonstrate_policy_denial()
        self.demonstrate_port_failure()

        self.controller.program_switch("vswitch-a")
        self.controller.program_switch("vswitch-b")

        print("\n=== Operational counters ===")
        for switch in self.switches.values():
            print(
                f"{switch.name}: "
                f"forwarded={switch.packet_forwards}, "
                f"dropped={switch.packet_drops}"
            )


def validate_network_design() -> None:
    print("\n=== Design validation ===")

    checks = {
        "IPv4 subnet parsing": lambda: ipaddress.ip_network("10.50.0.0/24"),
        "valid VNI range": lambda: OverlayNetwork("validation", 16_777_215),
        "invalid VNI detection": lambda: OverlayNetwork("invalid", 16_777_216),
        "invalid MAC detection": lambda: MACAddress("not-a-mac"),
    }

    for name, operation in checks.items():
        try:
            operation()
            print(f"{name}: PASS")
        except ValueError as exc:
            print(f"{name}: expected failure -> {exc}")


def main() -> None:
    random.seed(42)

    print("NETWORK VIRTUALIZATION LABORATORY")
    print("Virtual switching, segmentation, overlays, and SDN control")

    validate_network_design()

    lab = NetworkLab()
    lab.build()
    lab.run()

    print("\n=== Key architectural distinction ===")
    print(
        "The data plane forwards packets according to programmed forwarding "
        "state, while the control plane computes policy and topology intent."
    )
    print(
        "Virtual switches provide logical Layer-2 forwarding, virtual routers "
        "provide Layer-3 boundaries, and overlays allow logical networks to "
        "span an underlying transport network."
    )


if __name__ == "__main__":
    main()
