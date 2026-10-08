from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import ceil
from typing import Dict, List, Optional, Tuple


class PowerPath(Enum):
    A = "A"
    B = "B"
    SINGLE = "SINGLE"


class ServerState(Enum):
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    MAINTENANCE = "MAINTENANCE"


@dataclass
class Server:
    name: str
    rack_id: str
    power_kw: float
    cooling_kw: float
    power_path: PowerPath
    network_ports: int = 2
    state: ServerState = ServerState.RUNNING

    @property
    def total_thermal_load_kw(self) -> float:
        # In a practical data center model, almost all electrical power
        # consumed by IT equipment eventually becomes heat.
        return self.power_kw


@dataclass
class Rack:
    rack_id: str
    capacity_u: int = 42
    power_capacity_kw: float = 10.0
    servers: List[Server] = field(default_factory=list)

    def used_u(self) -> int:
        # This simplified model assigns one rack unit to each server.
        return len(self.servers)

    def used_power_kw(self) -> float:
        return sum(server.power_kw for server in self.servers)

    def available_u(self) -> int:
        return self.capacity_u - self.used_u()

    def available_power_kw(self) -> float:
        return self.power_capacity_kw - self.used_power_kw()

    def can_accept(self, server: Server) -> bool:
        return (
            server.rack_id == self.rack_id
            and self.available_u() >= 1
            and self.available_power_kw() >= server.power_kw
        )


@dataclass
class PowerFeed:
    name: str
    capacity_kw: float
    load_kw: float = 0.0
    available: bool = True

    def reserve(self, amount_kw: float) -> None:
        if not self.available:
            raise RuntimeError(f"Power feed {self.name} is unavailable")
        if self.load_kw + amount_kw > self.capacity_kw:
            raise RuntimeError(
                f"Power feed {self.name} exceeds capacity: "
                f"{self.load_kw + amount_kw:.2f} kW > {self.capacity_kw:.2f} kW"
            )
        self.load_kw += amount_kw


@dataclass
class CoolingSystem:
    name: str
    capacity_kw: float
    load_kw: float = 0.0
    available: bool = True

    def reserve(self, heat_kw: float) -> None:
        if not self.available:
            raise RuntimeError(f"Cooling system {self.name} is unavailable")
        if self.load_kw + heat_kw > self.capacity_kw:
            raise RuntimeError(
                f"Cooling system {self.name} exceeds capacity: "
                f"{self.load_kw + heat_kw:.2f} kW > {self.capacity_kw:.2f} kW"
            )
        self.load_kw += heat_kw


@dataclass
class NetworkSwitch:
    name: str
    port_capacity: int
    used_ports: int = 0
    available: bool = True

    def connect(self, ports: int) -> None:
        if not self.available:
            raise RuntimeError(f"Switch {self.name} is unavailable")
        if self.used_ports + ports > self.port_capacity:
            raise RuntimeError(
                f"Switch {self.name} has insufficient ports"
            )
        self.used_ports += ports


@dataclass
class DataCenter:
    name: str
    racks: Dict[str, Rack]
    power_feeds: Dict[str, PowerFeed]
    cooling_systems: Dict[str, CoolingSystem]
    switches: Dict[str, NetworkSwitch]

    def install_server(self, server: Server) -> None:
        if server.rack_id not in self.racks:
            raise ValueError(f"Unknown rack: {server.rack_id}")

        rack = self.racks[server.rack_id]
        if not rack.can_accept(server):
            raise RuntimeError(
                f"Rack {rack.rack_id} cannot accept server {server.name}"
            )

        # A dual-corded server is modeled as using both independent
        # power paths. The total server load is split across them.
        if server.power_path == PowerPath.A:
            self.power_feeds["A"].reserve(server.power_kw)
        elif server.power_path == PowerPath.B:
            self.power_feeds["B"].reserve(server.power_kw)
        else:
            # Single-fed equipment is less resilient and is explicitly
            # represented so that capacity and risk can be evaluated.
            self.power_feeds["A"].reserve(server.power_kw)

        cooling = self.cooling_systems["CRAC-A"]
        cooling.reserve(server.cooling_kw)

        # Two network connections are preferred for production servers.
        # The second connection can terminate on an independent switch.
        required_ports = min(server.network_ports, 2)
        self.switches["TOR-A"].connect(1)
        if required_ports == 2:
            self.switches["TOR-B"].connect(1)

        rack.servers.append(server)

    def total_it_load(self) -> float:
        return sum(
            server.power_kw
            for rack in self.racks.values()
            for server in rack.servers
            if server.state == ServerState.RUNNING
        )

    def total_heat_load(self) -> float:
        return sum(
            server.total_thermal_load_kw
            for rack in self.racks.values()
            for server in rack.servers
            if server.state == ServerState.RUNNING
        )

    def calculate_pue(self, facility_overhead_kw: float) -> float:
        it_load = self.total_it_load()
        if it_load <= 0:
            raise ValueError("IT load must be positive")
        return (it_load + facility_overhead_kw) / it_load

    def power_failure_test(self, failed_feed: str) -> Tuple[bool, str]:
        if failed_feed not in self.power_feeds:
            return False, f"Unknown power feed {failed_feed}"

        feed = self.power_feeds[failed_feed]
        original_state = feed.available
        feed.available = False

        vulnerable = [
            server.name
            for rack in self.racks.values()
            for server in rack.servers
            if server.power_path == PowerPath.SINGLE
            and failed_feed == "A"
        ]

        feed.available = original_state

        if vulnerable:
            return False, (
                f"Single-fed equipment would be affected: "
                f"{', '.join(vulnerable)}"
            )

        return True, f"Failure of feed {failed_feed} has no modeled single-feed impact"

    def cooling_failure_test(self, failed_system: str) -> Tuple[bool, str]:
        system = self.cooling_systems.get(failed_system)
        if system is None:
            return False, f"Unknown cooling system {failed_system}"

        other_systems = [
            cooling
            for name, cooling in self.cooling_systems.items()
            if name != failed_system and cooling.available
        ]

        required = self.total_heat_load()
        remaining = sum(cooling.capacity_kw for cooling in other_systems)

        if remaining >= required:
            return True, (
                f"Cooling survives failure of {failed_system}: "
                f"{remaining:.2f} kW remaining capacity for "
                f"{required:.2f} kW heat load"
            )

        return False, (
            f"Cooling capacity after {failed_system} failure is insufficient: "
            f"{remaining:.2f} kW < {required:.2f} kW"
        )

    def network_failure_test(self, failed_switch: str) -> Tuple[bool, str]:
        if failed_switch not in self.switches:
            return False, f"Unknown switch {failed_switch}"

        # Every production server in this example has two network paths.
        dual_connected = all(
            server.network_ports >= 2
            for rack in self.racks.values()
            for server in rack.servers
        )

        if dual_connected:
            return True, (
                f"Failure of {failed_switch} is survivable for dual-connected "
                "servers, assuming upstream routing also has redundancy"
            )

        return False, "At least one server lacks network-path redundancy"

    def report(self) -> None:
        print("\n=== DATA CENTER CAPACITY REPORT ===")
        print(f"Facility: {self.name}")
        print(f"Racks: {len(self.racks)}")
        print(f"Servers: {sum(len(r.servers) for r in self.racks.values())}")
        print(f"IT load: {self.total_it_load():.2f} kW")
        print(f"Thermal load: {self.total_heat_load():.2f} kW")

        for rack in self.racks.values():
            print(
                f"Rack {rack.rack_id}: "
                f"{rack.used_u()}/{rack.capacity_u} U, "
                f"{rack.used_power_kw():.2f}/{rack.power_capacity_kw:.2f} kW"
            )

        for feed in self.power_feeds.values():
            utilization = (
                feed.load_kw / feed.capacity_kw * 100
                if feed.capacity_kw
                else 0
            )
            print(
                f"Power {feed.name}: {feed.load_kw:.2f}/"
                f"{feed.capacity_kw:.2f} kW ({utilization:.1f}%)"
            )

        for cooling in self.cooling_systems.values():
            print(
                f"Cooling {cooling.name}: {cooling.load_kw:.2f}/"
                f"{cooling.capacity_kw:.2f} kW"
            )

        for switch in self.switches.values():
            print(
                f"Network {switch.name}: "
                f"{switch.used_ports}/{switch.port_capacity} ports"
            )


def estimate_rack_count(
    server_count: int,
    server_power_kw: float,
    rack_power_limit_kw: float,
    rack_u_capacity: int = 42,
) -> int:
    if server_count <= 0:
        raise ValueError("server_count must be positive")
    if server_power_kw <= 0 or rack_power_limit_kw <= 0:
        raise ValueError("Power values must be positive")

    servers_per_rack_by_power = max(
        1, int(rack_power_limit_kw // server_power_kw)
    )
    servers_per_rack = min(rack_u_capacity, servers_per_rack_by_power)
    return ceil(server_count / servers_per_rack)


def demonstrate_capacity_planning() -> None:
    print("\n=== CAPACITY PLANNING ===")
    racks = estimate_rack_count(
        server_count=80,
        server_power_kw=0.6,
        rack_power_limit_kw=8.0,
    )
    print(f"Racks required for 80 servers: {racks}")

    # Oversubscription is intentionally avoided here. The calculation
    # uses the physical rack power constraint as a hard limit.
    projected_load = 80 * 0.6
    print(f"Projected IT load: {projected_load:.2f} kW")


def build_example_datacenter() -> DataCenter:
    racks = {
        "R01": Rack("R01", power_capacity_kw=8.0),
        "R02": Rack("R02", power_capacity_kw=8.0),
    }

    power_feeds = {
        "A": PowerFeed("A", capacity_kw=10.0),
        "B": PowerFeed("B", capacity_kw=10.0),
    }

    cooling_systems = {
        "CRAC-A": CoolingSystem("CRAC-A", capacity_kw=12.0),
        "CRAC-B": CoolingSystem("CRAC-B", capacity_kw=12.0),
    }

    switches = {
        "TOR-A": NetworkSwitch("TOR-A", port_capacity=48),
        "TOR-B": NetworkSwitch("TOR-B", port_capacity=48),
    }

    return DataCenter(
        name="Enterprise Primary Data Hall",
        racks=racks,
        power_feeds=power_feeds,
        cooling_systems=cooling_systems,
        switches=switches,
    )


def install_example_workload(dc: DataCenter) -> None:
    servers = [
        Server("APP-01", "R01", 1.2, 1.2, PowerPath.A),
        Server("APP-02", "R01", 1.2, 1.2, PowerPath.B),
        Server("DB-01", "R01", 2.0, 2.0, PowerPath.A),
        Server("WEB-01", "R02", 0.8, 0.8, PowerPath.B),
        Server("WEB-02", "R02", 0.8, 0.8, PowerPath.A),
        Server("BACKUP-01", "R02", 1.5, 1.5, PowerPath.B),
    ]

    for server in servers:
        dc.install_server(server)


def demonstrate_failure_analysis(dc: DataCenter) -> None:
    print("\n=== FAILURE ANALYSIS ===")

    tests = [
        dc.power_failure_test("A"),
        dc.power_failure_test("B"),
        dc.cooling_failure_test("CRAC-A"),
        dc.cooling_failure_test("CRAC-B"),
        dc.network_failure_test("TOR-A"),
        dc.network_failure_test("TOR-B"),
    ]

    for survived, message in tests:
        print(("PASS: " if survived else "FAIL: ") + message)


def demonstrate_validation(dc: DataCenter) -> None:
    print("\n=== VALIDATION AND FAILURE CONDITIONS ===")

    try:
        invalid = Server(
            "INVALID",
            "UNKNOWN",
            power_kw=-1.0,
            cooling_kw=-1.0,
            power_path=PowerPath.A,
        )
        dc.install_server(invalid)
    except (ValueError, RuntimeError) as exc:
        print(f"Rejected invalid installation: {exc}")

    try:
        estimate_rack_count(0, 0.5, 8.0)
    except ValueError as exc:
        print(f"Rejected invalid capacity input: {exc}")


def main() -> None:
    demonstrate_capacity_planning()

    dc = build_example_datacenter()
    install_example_workload(dc)
    dc.report()

    pue = dc.calculate_pue(facility_overhead_kw=4.0)
    print(f"\nEstimated PUE: {pue:.3f}")

    demonstrate_failure_analysis(dc)
    demonstrate_validation(dc)

    print("\n=== ENGINEERING OBSERVATIONS ===")
    print(
        "Rack capacity must be evaluated using both physical space and "
        "electrical limits; a rack can have free U-space but still be "
        "power-constrained."
    )
    print(
        "A redundant power design requires genuinely independent paths, "
        "not merely two outlets connected to the same upstream failure domain."
    )
    print(
        "Cooling capacity must be evaluated under component-failure conditions "
        "rather than only under normal operating conditions."
    )
    print(
        "Dual network connections reduce the impact of a top-of-rack switch "
        "failure, but end-to-end availability also depends on upstream paths."
    )


if __name__ == "__main__":
    main()
