#!/usr/bin/env python3
"""
Cloud Network Security Policy Simulator

Implements:
- Stateful security groups
- Stateless network ACLs
- Ordered firewall rules
- CIDR and port-range validation
- Inbound and outbound traffic evaluation
- Connection tracking
- Policy auditing and rule-conflict detection
- JSON policy export
- Automated security tests

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import ipaddress
import json
import logging
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)
logger = logging.getLogger("cloud-security")


class Direction(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class Action(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class Protocol(str, Enum):
    TCP = "tcp"
    UDP = "udp"
    ICMP = "icmp"
    ALL = "all"


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


@dataclass(frozen=True)
class Packet:
    source_ip: str
    destination_ip: str
    protocol: Protocol
    source_port: int = 0
    destination_port: int = 0

    def __post_init__(self):
        try:
            ipaddress.ip_address(self.source_ip)
            ipaddress.ip_address(self.destination_ip)
        except ValueError as exc:
            raise ValueError("Invalid packet IP address") from exc

        if not 0 <= self.source_port <= 65535:
            raise ValueError("Invalid source port")

        if not 0 <= self.destination_port <= 65535:
            raise ValueError("Invalid destination port")

        if self.protocol in (Protocol.ICMP, Protocol.ALL):
            if self.source_port != 0 or self.destination_port != 0:
                raise ValueError("ICMP and ALL packets must use zero ports")


@dataclass(frozen=True)
class NetworkRule:
    rule_id: str
    direction: Direction
    action: Action
    protocol: Protocol
    cidr: str
    port_start: int = 0
    port_end: int = 65535
    priority: int = 100
    description: str = ""

    def __post_init__(self):
        if not self.rule_id.strip():
            raise ValueError("Rule ID cannot be empty")

        try:
            ipaddress.ip_network(self.cidr, strict=False)
        except ValueError as exc:
            raise ValueError(f"Invalid CIDR: {self.cidr}") from exc

        if not 0 <= self.port_start <= self.port_end <= 65535:
            raise ValueError("Invalid port range")

        if self.priority < 0:
            raise ValueError("Priority cannot be negative")

        if self.protocol in (Protocol.ICMP, Protocol.ALL):
            if self.port_start != 0 or self.port_end != 65535:
                raise ValueError("ICMP and ALL rules must use the full port range")

    def matches(self, packet: Packet, direction: Direction) -> bool:
        if self.direction != direction:
            return False

        address = (
            packet.source_ip
            if direction == Direction.INBOUND
            else packet.destination_ip
        )

        if ipaddress.ip_address(address) not in ipaddress.ip_network(
            self.cidr, strict=False
        ):
            return False

        if self.protocol != Protocol.ALL:
            if self.protocol != packet.protocol:
                return False

        if packet.protocol in (Protocol.ICMP, Protocol.ALL):
            return True

        port = (
            packet.destination_port
            if direction == Direction.INBOUND
            else packet.destination_port
        )

        return self.port_start <= port <= self.port_end


@dataclass
class Evaluation:
    decision: Decision
    layer: str
    reason: str
    matched_rule: Optional[str] = None


@dataclass
class ConnectionTracker:
    """Tracks established TCP/UDP flows for stateful security groups."""

    established: set[tuple] = field(default_factory=set)

    @staticmethod
    def connection_key(packet: Packet) -> tuple:
        return (
            packet.source_ip,
            packet.destination_ip,
            packet.protocol.value,
            packet.source_port,
            packet.destination_port
        )

    def contains(self, packet: Packet) -> bool:
        forward = self.connection_key(packet)
        reverse = (
            packet.destination_ip,
            packet.source_ip,
            packet.protocol.value,
            packet.destination_port,
            packet.source_port
        )
        return forward in self.established or reverse in self.established

    def add(self, packet: Packet) -> None:
        self.established.add(self.connection_key(packet))


class SecurityGroup:
    """
    Stateful virtual-machine or network-interface policy.

    Security groups have allow rules only. Unmatched traffic is denied.
    Return traffic for established connections is automatically permitted.
    """

    def __init__(self, name: str):
        self.name = name
        self.rules: list[NetworkRule] = []
        self.connections = ConnectionTracker()

    def add_rule(self, rule: NetworkRule) -> None:
        if rule.action != Action.ALLOW:
            raise ValueError("Security groups support ALLOW rules only")

        if any(existing.rule_id == rule.rule_id for existing in self.rules):
            raise ValueError("Duplicate security group rule ID")

        self.rules.append(rule)

    def evaluate(
        self,
        packet: Packet,
        direction: Direction
    ) -> Evaluation:

        if self.connections.contains(packet):
            return Evaluation(
                Decision.ALLOW,
                "security_group",
                "Established connection"
            )

        for rule in self.rules:
            if rule.matches(packet, direction):
                if direction == Direction.OUTBOUND:
                    self.connections.add(packet)

                return Evaluation(
                    Decision.ALLOW,
                    "security_group",
                    "Explicit security group allow",
                    rule.rule_id
                )

        return Evaluation(
            Decision.DENY,
            "security_group",
            "No matching allow rule"
        )


class NetworkACL:
    """
    Stateless subnet-level access control.

    Rules are evaluated in ascending priority order.
    Both request and response directions require explicit permission.
    """

    def __init__(self, name: str):
        self.name = name
        self.rules: list[NetworkRule] = []

    def add_rule(self, rule: NetworkRule) -> None:
        if any(existing.rule_id == rule.rule_id for existing in self.rules):
            raise ValueError("Duplicate network ACL rule ID")

        self.rules.append(rule)
        self.rules.sort(key=lambda item: item.priority)

    def evaluate(
        self,
        packet: Packet,
        direction: Direction
    ) -> Evaluation:

        for rule in self.rules:
            if rule.matches(packet, direction):
                return Evaluation(
                    Decision(rule.action.value.upper()),
                    "network_acl",
                    f"Matched priority {rule.priority}",
                    rule.rule_id
                )

        return Evaluation(
            Decision.DENY,
            "network_acl",
            "Default deny: no matching ACL rule"
        )


class Firewall:
    """
    Ordered stateful firewall.

    First matching rule determines the decision.
    No matching rule results in an explicit default-deny decision.
    """

    def __init__(self, name: str):
        self.name = name
        self.rules: list[NetworkRule] = []

    def add_rule(self, rule: NetworkRule) -> None:
        if any(existing.rule_id == rule.rule_id for existing in self.rules):
            raise ValueError("Duplicate firewall rule ID")

        self.rules.append(rule)
        self.rules.sort(key=lambda item: item.priority)

    def evaluate(
        self,
        packet: Packet,
        direction: Direction
    ) -> Evaluation:

        for rule in self.rules:
            if rule.matches(packet, direction):
                return Evaluation(
                    Decision(rule.action.value.upper()),
                    "firewall",
                    f"First matching rule at priority {rule.priority}",
                    rule.rule_id
                )

        return Evaluation(
            Decision.DENY,
            "firewall",
            "Firewall default deny"
        )


class CloudNetwork:
    """
    Combines independent network security layers.

    Traffic must pass all configured security controls.
    """

    def __init__(
        self,
        security_group: SecurityGroup,
        network_acl: NetworkACL,
        firewall: Firewall
    ):
        self.security_group = security_group
        self.network_acl = network_acl
        self.firewall = firewall

    def inspect(
        self,
        packet: Packet,
        direction: Direction
    ) -> Evaluation:

        layers = (
            self.network_acl,
            self.security_group,
            self.firewall
        )

        for layer in layers:
            result = layer.evaluate(packet, direction)

            logger.info(
                "%s | %s | %s",
                layer.__class__.__name__,
                result.decision.value,
                result.reason
            )

            if result.decision == Decision.DENY:
                return result

        return Evaluation(
            Decision.ALLOW,
            "cloud_network",
            "All security layers permitted traffic"
        )

    def audit(self) -> dict:
        return {
            "security_group_rules": len(self.security_group.rules),
            "network_acl_rules": len(self.network_acl.rules),
            "firewall_rules": len(self.firewall.rules),
            "security_group_allows_only": all(
                r.action == Action.ALLOW
                for r in self.security_group.rules
            ),
            "duplicate_ids": self._duplicate_ids()
        }

    def _duplicate_ids(self) -> list[str]:
        ids = [
            rule.rule_id
            for layer in (
                self.security_group,
                self.network_acl,
                self.firewall
            )
            for rule in layer.rules
        ]
        return sorted({
            item for item in ids if ids.count(item) > 1
        })

    def export_policy(self, destination: Path) -> None:
        data = {
            "security_group": [
                self._serialize_rule(r)
                for r in self.security_group.rules
            ],
            "network_acl": [
                self._serialize_rule(r)
                for r in self.network_acl.rules
            ],
            "firewall": [
                self._serialize_rule(r)
                for r in self.firewall.rules
            ]
        }

        destination.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8"
        )

    @staticmethod
    def _serialize_rule(rule: NetworkRule) -> dict:
        data = asdict(rule)
        for key, value in data.items():
            if isinstance(value, Enum):
                data[key] = value.value
        return data


def build_demo_environment() -> CloudNetwork:
    security_group = SecurityGroup("application-sg")

    security_group.add_rule(NetworkRule(
        "sg-https",
        Direction.INBOUND,
        Action.ALLOW,
        Protocol.TCP,
        "0.0.0.0/0",
        443,
        443,
        description="Public HTTPS"
    ))

    security_group.add_rule(NetworkRule(
        "sg-ssh",
        Direction.INBOUND,
        Action.ALLOW,
        Protocol.TCP,
        "10.0.1.0/24",
        22,
        22,
        description="Administrative subnet"
    ))

    security_group.add_rule(NetworkRule(
        "sg-db-out",
        Direction.OUTBOUND,
        Action.ALLOW,
        Protocol.TCP,
        "10.0.2.0/24",
        5432,
        5432,
        description="Database connectivity"
    ))

    acl = NetworkACL("application-subnet-acl")

    acl.add_rule(NetworkRule(
        "acl-https",
        Direction.INBOUND,
        Action.ALLOW,
        Protocol.TCP,
        "0.0.0.0/0",
        443,
        443,
        100
    ))

    acl.add_rule(NetworkRule(
        "acl-ssh",
        Direction.INBOUND,
        Action.ALLOW,
        Protocol.TCP,
        "10.0.1.0/24",
        22,
        22,
        110
    ))

    acl.add_rule(NetworkRule(
        "acl-return",
        Direction.OUTBOUND,
        Action.ALLOW,
        Protocol.TCP,
        "0.0.0.0/0",
        0,
        65535,
        100
    ))

    firewall = Firewall("perimeter-firewall")

    firewall.add_rule(NetworkRule(
        "fw-block-malicious",
        Direction.INBOUND,
        Action.DENY,
        Protocol.ALL,
        "198.51.100.0/24",
        priority=10
    ))

    firewall.add_rule(NetworkRule(
        "fw-allow-https",
        Direction.INBOUND,
        Action.ALLOW,
        Protocol.TCP,
        "0.0.0.0/0",
        443,
        443,
        priority=100
    ))

    firewall.add_rule(NetworkRule(
        "fw-allow-ssh",
        Direction.INBOUND,
        Action.ALLOW,
        Protocol.TCP,
        "10.0.1.0/24",
        22,
        22,
        priority=110
    ))

    firewall.add_rule(NetworkRule(
        "fw-outbound",
        Direction.OUTBOUND,
        Action.ALLOW,
        Protocol.ALL,
        "0.0.0.0/0",
        priority=100
    ))

    return CloudNetwork(security_group, acl, firewall)


def run_tests(network: CloudNetwork) -> None:
    https = Packet(
        "203.0.113.10",
        "10.0.0.10",
        Protocol.TCP,
        51000,
        443
    )

    result = network.inspect(https, Direction.INBOUND)
    assert result.decision == Decision.ALLOW

    # Stateful security groups permit established return traffic.
    response = Packet(
        "10.0.0.10",
        "203.0.113.10",
        Protocol.TCP,
        443,
        51000
    )

    result = network.inspect(response, Direction.OUTBOUND)
    assert result.decision == Decision.ALLOW

    blocked = Packet(
        "198.51.100.20",
        "10.0.0.10",
        Protocol.TCP,
        51000,
        443
    )

    result = network.inspect(blocked, Direction.INBOUND)
    assert result.decision == Decision.DENY

    unauthorized_ssh = Packet(
        "203.0.113.20",
        "10.0.0.10",
        Protocol.TCP,
        51001,
        22
    )

    result = network.inspect(unauthorized_ssh, Direction.INBOUND)
    assert result.decision == Decision.DENY

    print("All security tests passed.")


def main() -> None:
    network = build_demo_environment()

    print("\nCLOUD NETWORK SECURITY SIMULATOR")
    print("=" * 45)

    run_tests(network)

    print("\nPolicy audit:")
    print(json.dumps(network.audit(), indent=2))

    print("\nExporting policy...")
    output = Path("cloud_security_policy.json")
    network.export_policy(output)
    print(f"Policy exported to {output.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        logger.error("Execution failed: %s", exc)
        raise SystemExit(1)
