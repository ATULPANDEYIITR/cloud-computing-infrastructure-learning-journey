from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


class LoadBalancerType(Enum):
    APPLICATION = "application"
    NETWORK = "network"


class TargetState(Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DRAINING = "draining"


class Protocol(Enum):
    HTTP = "HTTP"
    HTTPS = "HTTPS"
    TCP = "TCP"
    TLS = "TLS"


@dataclass
class HealthCheck:
    protocol: Protocol
    port: int
    path: Optional[str] = None
    interval_seconds: int = 10
    timeout_seconds: int = 5
    healthy_threshold: int = 2
    unhealthy_threshold: int = 3

    def validate(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError("Health-check port must be between 1 and 65535.")
        if self.protocol in {Protocol.HTTP, Protocol.HTTPS} and not self.path:
            raise ValueError("HTTP/HTTPS health checks require a path.")
        if self.interval_seconds <= 0 or self.timeout_seconds <= 0:
            raise ValueError("Health-check timing values must be positive.")
        if self.timeout_seconds >= self.interval_seconds:
            raise ValueError("Health-check timeout must be shorter than its interval.")


@dataclass
class Target:
    target_id: str
    address: str
    port: int
    state: TargetState = TargetState.HEALTHY
    active_connections: int = 0
    metadata: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.target_id.strip():
            raise ValueError("Target ID cannot be empty.")
        if not self.address.strip():
            raise ValueError("Target address cannot be empty.")
        if not 1 <= self.port <= 65535:
            raise ValueError("Target port must be between 1 and 65535.")
        if self.active_connections < 0:
            raise ValueError("Active connections cannot be negative.")


@dataclass
class TargetGroup:
    name: str
    protocol: Protocol
    port: int
    health_check: HealthCheck
    targets: Dict[str, Target] = field(default_factory=dict)

    def add_target(self, target: Target) -> None:
        target.validate()
        if target.target_id in self.targets:
            raise ValueError(f"Target already exists: {target.target_id}")
        if target.port != self.port:
            raise ValueError(
                f"Target {target.target_id} uses port {target.port}, "
                f"but target group expects {self.port}."
            )
        self.targets[target.target_id] = target

    def healthy_targets(self) -> List[Target]:
        return [
            target
            for target in self.targets.values()
            if target.state == TargetState.HEALTHY
        ]

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Target-group name cannot be empty.")
        if not 1 <= self.port <= 65535:
            raise ValueError("Target-group port must be between 1 and 65535.")
        self.health_check.validate()
        for target in self.targets.values():
            target.validate()


@dataclass
class Request:
    request_id: str
    protocol: Protocol
    host: Optional[str] = None
    path: Optional[str] = None
    source_ip: Optional[str] = None


@dataclass
class Listener:
    protocol: Protocol
    port: int
    target_group: str

    def validate(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError("Listener port must be between 1 and 65535.")
        if self.protocol in {Protocol.HTTP, Protocol.HTTPS}:
            if self.port not in {80, 443}:
                raise ValueError("HTTP/HTTPS listeners use the conventional ports 80/443.")


class LoadBalancer:
    """
    Educational simulation of two common cloud load-balancing models.

    Application load balancing makes Layer-7 decisions such as host/path routing.
    Network load balancing models Layer-4 forwarding using a deterministic flow hash.
    """

    def __init__(self, name: str, lb_type: LoadBalancerType) -> None:
        self.name = name
        self.lb_type = lb_type
        self.target_groups: Dict[str, TargetGroup] = {}
        self.listeners: Dict[Tuple[Protocol, int], Listener] = {}
        self._round_robin_index: Dict[str, int] = {}

    def add_target_group(self, group: TargetGroup) -> None:
        group.validate()
        if group.name in self.target_groups:
            raise ValueError(f"Target group already exists: {group.name}")
        self.target_groups[group.name] = group

    def add_listener(self, listener: Listener) -> None:
        listener.validate()
        key = (listener.protocol, listener.port)
        if key in self.listeners:
            raise ValueError(f"Listener already exists on {listener.protocol.value}:{listener.port}")
        if listener.target_group not in self.target_groups:
            raise ValueError(f"Unknown target group: {listener.target_group}")
        self.listeners[key] = listener

    def mark_target(
        self,
        group_name: str,
        target_id: str,
        state: TargetState,
    ) -> None:
        group = self._get_group(group_name)
        if target_id not in group.targets:
            raise KeyError(f"Unknown target: {target_id}")
        group.targets[target_id].state = state

    def _get_group(self, name: str) -> TargetGroup:
        try:
            return self.target_groups[name]
        except KeyError as exc:
            raise KeyError(f"Unknown target group: {name}") from exc

    def _select_application_target(self, request: Request, group: TargetGroup) -> Target:
        healthy = group.healthy_targets()
        if not healthy:
            raise RuntimeError("No healthy targets are available.")

        # Simple round-robin represents an L7 routing decision.
        index = self._round_robin_index.get(group.name, 0) % len(healthy)
        target = healthy[index]
        self._round_robin_index[group.name] = index + 1
        return target

    def _select_network_target(self, request: Request, group: TargetGroup) -> Target:
        healthy = group.healthy_targets()
        if not healthy:
            raise RuntimeError("No healthy targets are available.")

        # A stable flow key approximates flow-aware Layer-4 distribution.
        flow = "|".join(
            [
                request.source_ip or "",
                request.protocol.value,
                request.host or "",
                request.path or "",
            ]
        )
        bucket = sum(ord(char) * (position + 1) for position, char in enumerate(flow))
        return healthy[bucket % len(healthy)]

    def route(self, request: Request) -> str:
        listener = self.listeners.get((request.protocol, self._default_port(request.protocol)))
        if listener is None:
            raise RuntimeError(
                f"No listener for {request.protocol.value}:{self._default_port(request.protocol)}"
            )

        group = self._get_group(listener.target_group)

        if self.lb_type == LoadBalancerType.APPLICATION:
            if request.protocol not in {Protocol.HTTP, Protocol.HTTPS}:
                raise RuntimeError("Application load balancing requires HTTP/HTTPS traffic.")
            target = self._select_application_target(request, group)
        else:
            if request.protocol not in {Protocol.TCP, Protocol.TLS}:
                raise RuntimeError("Network load balancing requires TCP/TLS traffic.")
            target = self._select_network_target(request, group)

        target.active_connections += 1
        return target.target_id

    @staticmethod
    def _default_port(protocol: Protocol) -> int:
        return {
            Protocol.HTTP: 80,
            Protocol.HTTPS: 443,
            Protocol.TCP: 443,
            Protocol.TLS: 443,
        }[protocol]

    def connection_closed(self, group_name: str, target_id: str) -> None:
        group = self._get_group(group_name)
        target = group.targets.get(target_id)
        if target is None:
            raise KeyError(f"Unknown target: {target_id}")
        if target.active_connections == 0:
            raise RuntimeError("Cannot close a connection when none are active.")
        target.active_connections -= 1

    def drain_target(self, group_name: str, target_id: str) -> None:
        group = self._get_group(group_name)
        target = group.targets.get(target_id)
        if target is None:
            raise KeyError(f"Unknown target: {target_id}")
        target.state = TargetState.DRAINING

    def health_report(self) -> Dict[str, Dict[str, str]]:
        report: Dict[str, Dict[str, str]] = {}
        for group_name, group in self.target_groups.items():
            report[group_name] = {
                target.target_id: target.state.value
                for target in group.targets.values()
            }
        return report


def build_application_example() -> LoadBalancer:
    lb = LoadBalancer("web-alb", LoadBalancerType.APPLICATION)

    health = HealthCheck(
        protocol=Protocol.HTTP,
        port=8080,
        path="/health",
        interval_seconds=10,
        timeout_seconds=3,
        healthy_threshold=2,
        unhealthy_threshold=3,
    )

    group = TargetGroup(
        name="web-targets",
        protocol=Protocol.HTTP,
        port=8080,
        health_check=health,
    )

    group.add_target(Target("web-1", "10.0.1.10", 8080, metadata={"zone": "a"}))
    group.add_target(Target("web-2", "10.0.2.10", 8080, metadata={"zone": "b"}))
    group.add_target(Target("web-3", "10.0.3.10", 8080, metadata={"zone": "c"}))

    lb.add_target_group(group)
    lb.add_listener(Listener(Protocol.HTTP, 80, "web-targets"))
    return lb


def build_network_example() -> LoadBalancer:
    lb = LoadBalancer("tcp-nlb", LoadBalancerType.NETWORK)

    health = HealthCheck(
        protocol=Protocol.TCP,
        port=9000,
        interval_seconds=10,
        timeout_seconds=3,
        healthy_threshold=2,
        unhealthy_threshold=3,
    )

    group = TargetGroup(
        name="tcp-targets",
        protocol=Protocol.TCP,
        port=9000,
        health_check=health,
    )

    group.add_target(Target("tcp-1", "10.0.10.10", 9000))
    group.add_target(Target("tcp-2", "10.0.20.10", 9000))

    lb.add_target_group(group)
    lb.add_listener(Listener(Protocol.TCP, 443, "tcp-targets"))
    return lb


def main() -> None:
    print("=== Application Load Balancer ===")
    alb = build_application_example()

    requests = [
        Request("req-1", Protocol.HTTP, "api.example.com", "/users", "192.0.2.10"),
        Request("req-2", Protocol.HTTP, "api.example.com", "/orders", "192.0.2.11"),
        Request("req-3", Protocol.HTTP, "api.example.com", "/health", "192.0.2.12"),
    ]

    for request in requests:
        target = alb.route(request)
        print(f"{request.request_id} -> {target}")

    alb.mark_target("web-targets", "web-2", TargetState.UNHEALTHY)
    print("Health:", alb.health_report())

    try:
        target = alb.route(Request("req-4", Protocol.HTTP, "api.example.com", "/users"))
        print(f"req-4 -> {target}")
    except RuntimeError as exc:
        print("Routing failure:", exc)

    print("\n=== Network Load Balancer ===")
    nlb = build_network_example()

    for request in [
        Request("flow-1", Protocol.TCP, source_ip="198.51.100.10"),
        Request("flow-2", Protocol.TCP, source_ip="198.51.100.11"),
        Request("flow-3", Protocol.TCP, source_ip="198.51.100.10"),
    ]:
        print(f"{request.request_id} -> {nlb.route(request)}")

    nlb.drain_target("tcp-targets", "tcp-1")
    print("After draining tcp-1:", nlb.health_report())

    # Assertions provide executable sanity checks without external test packages.
    assert len(alb.target_groups["web-targets"].targets) == 3
    assert "web-2" in alb.health_report()["web-targets"]
    assert nlb.target_groups["tcp-targets"].targets["tcp-1"].state == TargetState.DRAINING


if __name__ == "__main__":
    main()
