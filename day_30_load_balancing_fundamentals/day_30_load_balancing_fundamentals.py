#!/usr/bin/env python3
"""
Load Balancing Fundamentals
Layer 4, Layer 7, traffic distribution, health checks, and sticky sessions.

This self-contained program models a small load-balancing environment without
external packages. It demonstrates:

- Layer 4 connection-oriented routing
- Layer 7 HTTP-aware routing
- Multiple traffic-distribution algorithms
- Active and passive health checks
- Sticky sessions
- Connection lifecycle and backend capacity
- Failure handling and recovery
- Weighted routing
- Request simulation and operational metrics

The implementation is intentionally a simulation rather than a real network
proxy. It models the decisions a load balancer makes while keeping all network
I/O local and deterministic.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
import random
import time
from typing import Callable, Optional


class Protocol(str, Enum):
    TCP = "TCP"
    HTTP = "HTTP"


class BackendState(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DRAINING = "draining"


@dataclass
class Request:
    request_id: int
    client_ip: str
    protocol: Protocol
    path: str = "/"
    method: str = "GET"
    session_id: Optional[str] = None
    headers: dict[str, str] = field(default_factory=dict)
    payload_size: int = 0


@dataclass
class HealthCheckResult:
    backend_id: str
    healthy: bool
    latency_ms: float
    reason: str


@dataclass
class BackendServer:
    backend_id: str
    host: str
    port: int
    weight: int = 1
    state: BackendState = BackendState.HEALTHY
    base_latency_ms: float = 20.0
    max_connections: int = 100
    active_connections: int = 0
    total_requests: int = 0
    failed_requests: int = 0
    health_failures: int = 0
    health_successes: int = 0
    metadata: dict[str, str] = field(default_factory=dict)

    def can_accept(self) -> bool:
        return (
            self.state == BackendState.HEALTHY
            and self.active_connections < self.max_connections
        )

    def begin_request(self) -> bool:
        if not self.can_accept():
            return False
        self.active_connections += 1
        self.total_requests += 1
        return True

    def finish_request(self, success: bool = True) -> None:
        self.active_connections = max(0, self.active_connections - 1)
        if not success:
            self.failed_requests += 1


class RoundRobinBalancer:
    """Distributes requests sequentially among eligible backends."""

    def __init__(self) -> None:
        self.cursor = 0

    def select(self, backends: list[BackendServer]) -> Optional[BackendServer]:
        eligible = [b for b in backends if b.can_accept()]
        if not eligible:
            return None

        selected = eligible[self.cursor % len(eligible)]
        self.cursor = (self.cursor + 1) % len(eligible)
        return selected


class WeightedRoundRobinBalancer:
    """Uses configured backend weights to represent different capacities."""

    def __init__(self) -> None:
        self.cursor = 0

    def select(self, backends: list[BackendServer]) -> Optional[BackendServer]:
        eligible = [b for b in backends if b.can_accept() and b.weight > 0]
        if not eligible:
            return None

        expanded: list[BackendServer] = []
        for backend in eligible:
            expanded.extend([backend] * backend.weight)

        selected = expanded[self.cursor % len(expanded)]
        self.cursor = (self.cursor + 1) % len(expanded)
        return selected


class LeastConnectionsBalancer:
    """Routes to the eligible backend carrying the fewest active connections."""

    def select(self, backends: list[BackendServer]) -> Optional[BackendServer]:
        eligible = [b for b in backends if b.can_accept()]
        if not eligible:
            return None

        return min(
            eligible,
            key=lambda backend: (backend.active_connections, -backend.weight),
        )


class IPHashBalancer:
    """Provides deterministic client-IP affinity without storing sessions."""

    def select(
        self,
        backends: list[BackendServer],
        client_ip: str,
    ) -> Optional[BackendServer]:
        eligible = [b for b in backends if b.can_accept()]
        if not eligible:
            return None

        index = hash(client_ip) % len(eligible)
        return eligible[index]


class StickySessionBalancer:
    """
    Application-level session affinity.

    A session is mapped to a backend. If that backend becomes unavailable,
    the mapping is invalidated and normal selection is used to recover.
    """

    def __init__(self, fallback: Callable[[list[BackendServer]], Optional[BackendServer]]):
        self.fallback = fallback
        self.session_map: dict[str, str] = {}

    def select(
        self,
        backends: list[BackendServer],
        session_id: Optional[str],
    ) -> Optional[BackendServer]:
        eligible = {b.backend_id: b for b in backends if b.can_accept()}

        if session_id:
            mapped_id = self.session_map.get(session_id)
            if mapped_id in eligible:
                return eligible[mapped_id]

        selected = self.fallback(backends)
        if selected and session_id:
            self.session_map[session_id] = selected.backend_id

        return selected

    def remove_backend(self, backend_id: str) -> None:
        self.session_map = {
            session: backend
            for session, backend in self.session_map.items()
            if backend != backend_id
        }


class HealthChecker:
    """
    Simulates active health checks.

    Real systems usually perform network-level checks such as TCP connection
    establishment or HTTP requests. Here the backend metadata controls whether
    the simulated endpoint is considered healthy.
    """

    def __init__(self, timeout_ms: float = 500.0) -> None:
        self.timeout_ms = timeout_ms

    def check(self, backend: BackendServer) -> HealthCheckResult:
        start = time.perf_counter()

        configured_status = backend.metadata.get("health", "ok")
        simulated_latency = backend.base_latency_ms

        healthy = (
            configured_status == "ok"
            and backend.state != BackendState.DRAINING
            and simulated_latency <= self.timeout_ms
        )

        elapsed = (time.perf_counter() - start) * 1000
        latency = max(elapsed, simulated_latency)

        if healthy:
            backend.health_successes += 1
            reason = "health endpoint accepted the check"
        else:
            backend.health_failures += 1
            reason = "health endpoint failed or exceeded policy"

        return HealthCheckResult(
            backend_id=backend.backend_id,
            healthy=healthy,
            latency_ms=latency,
            reason=reason,
        )


class LoadBalancer:
    """
    A small load-balancer controller.

    Layer 4 routing makes its decision primarily from transport-level
    information such as protocol and client address.

    Layer 7 routing can inspect HTTP method, path, headers, and other
    application metadata before choosing a backend.
    """

    def __init__(
        self,
        backends: list[BackendServer],
        algorithm: str = "round_robin",
    ) -> None:
        self.backends = backends
        self.round_robin = RoundRobinBalancer()
        self.weighted = WeightedRoundRobinBalancer()
        self.least_connections = LeastConnectionsBalancer()
        self.ip_hash = IPHashBalancer()
        self.sticky = StickySessionBalancer(self.round_robin.select)
        self.algorithm = algorithm
        self.health_checker = HealthChecker()
        self.request_count = 0
        self.failed_routing = 0
        self.path_routes: dict[str, str] = {}

    def run_health_checks(self) -> list[HealthCheckResult]:
        results = []

        for backend in self.backends:
            result = self.health_checker.check(backend)
            results.append(result)

            if result.healthy:
                if backend.state == BackendState.UNHEALTHY:
                    backend.state = BackendState.HEALTHY
            else:
                backend.state = BackendState.UNHEALTHY

        return results

    def select_backend(self, request: Request) -> Optional[BackendServer]:
        """
        Select a backend according to the configured policy.

        Path-specific routing is an L7 feature. For example, /api requests
        can be sent to an API pool while /assets requests can use an asset pool.
        """

        if request.protocol == Protocol.HTTP:
            explicit_backend = self.path_routes.get(request.path)
            if explicit_backend:
                candidate = next(
                    (
                        backend
                        for backend in self.backends
                        if backend.backend_id == explicit_backend
                        and backend.can_accept()
                    ),
                    None,
                )
                if candidate:
                    return candidate

        if self.algorithm == "round_robin":
            return self.round_robin.select(self.backends)

        if self.algorithm == "weighted":
            return self.weighted.select(self.backends)

        if self.algorithm == "least_connections":
            return self.least_connections.select(self.backends)

        if self.algorithm == "ip_hash":
            return self.ip_hash.select(self.backends, request.client_ip)

        if self.algorithm == "sticky":
            return self.sticky.select(self.backends, request.session_id)

        raise ValueError(f"Unknown load-balancing algorithm: {self.algorithm}")

    def process_request(self, request: Request) -> dict[str, object]:
        self.request_count += 1
        backend = self.select_backend(request)

        if backend is None:
            self.failed_routing += 1
            return {
                "request_id": request.request_id,
                "success": False,
                "reason": "no healthy backend with available capacity",
            }

        accepted = backend.begin_request()
        if not accepted:
            self.failed_routing += 1
            return {
                "request_id": request.request_id,
                "success": False,
                "reason": "backend rejected the connection",
            }

        # Application-level failures are simulated independently from routing.
        success = backend.metadata.get("application_status", "ok") == "ok"
        backend.finish_request(success=success)

        return {
            "request_id": request.request_id,
            "success": success,
            "backend": backend.backend_id,
            "protocol": request.protocol.value,
            "path": request.path,
            "session": request.session_id,
        }

    def configure_path_route(self, path: str, backend_id: str) -> None:
        if not path.startswith("/"):
            raise ValueError("HTTP paths must begin with '/'")

        if not any(b.backend_id == backend_id for b in self.backends):
            raise ValueError(f"Unknown backend: {backend_id}")

        self.path_routes[path] = backend_id

    def drain_backend(self, backend_id: str) -> None:
        backend = self._find_backend(backend_id)
        backend.state = BackendState.DRAINING
        self.sticky.remove_backend(backend_id)

    def restore_backend(self, backend_id: str) -> None:
        backend = self._find_backend(backend_id)
        backend.state = BackendState.HEALTHY
        backend.metadata["health"] = "ok"

    def _find_backend(self, backend_id: str) -> BackendServer:
        for backend in self.backends:
            if backend.backend_id == backend_id:
                return backend
        raise KeyError(f"Backend {backend_id!r} does not exist")

    def metrics(self) -> dict[str, object]:
        return {
            "requests": self.request_count,
            "routing_failures": self.failed_routing,
            "backend_requests": {
                backend.backend_id: backend.total_requests
                for backend in self.backends
            },
            "backend_failures": {
                backend.backend_id: backend.failed_requests
                for backend in self.backends
            },
        }


def build_demo_backends() -> list[BackendServer]:
    return [
        BackendServer(
            backend_id="web-01",
            host="10.0.1.11",
            port=8080,
            weight=3,
            base_latency_ms=15,
            metadata={"role": "web", "health": "ok"},
        ),
        BackendServer(
            backend_id="web-02",
            host="10.0.1.12",
            port=8080,
            weight=2,
            base_latency_ms=25,
            metadata={"role": "web", "health": "ok"},
        ),
        BackendServer(
            backend_id="web-03",
            host="10.0.1.13",
            port=8080,
            weight=1,
            base_latency_ms=35,
            metadata={"role": "web", "health": "ok"},
        ),
    ]


def demonstrate_layer4() -> None:
    print("\n=== Layer 4: transport-level distribution ===")

    backends = build_demo_backends()
    balancer = LoadBalancer(backends, algorithm="round_robin")

    requests = [
        Request(
            request_id=index,
            client_ip=f"192.168.10.{index}",
            protocol=Protocol.TCP,
        )
        for index in range(1, 10)
    ]

    results = [balancer.process_request(request) for request in requests]
    distribution = Counter(
        result["backend"] for result in results if result.get("success")
    )

    print("TCP connection distribution:", dict(distribution))
    print(
        "Layer 4 does not need to understand HTTP paths such as "
        "'/api/orders' to distribute TCP connections."
    )


def demonstrate_layer7() -> None:
    print("\n=== Layer 7: HTTP-aware routing ===")

    backends = build_demo_backends()
    balancer = LoadBalancer(backends, algorithm="round_robin")

    balancer.configure_path_route("/api/orders", "web-01")
    balancer.configure_path_route("/static/logo.svg", "web-03")

    requests = [
        Request(101, "10.10.0.1", Protocol.HTTP, "/api/orders"),
        Request(102, "10.10.0.2", Protocol.HTTP, "/static/logo.svg"),
        Request(103, "10.10.0.3", Protocol.HTTP, "/"),
    ]

    for request in requests:
        print(balancer.process_request(request))


def demonstrate_algorithms() -> None:
    print("\n=== Traffic distribution algorithms ===")

    algorithms = [
        "round_robin",
        "weighted",
        "least_connections",
        "ip_hash",
    ]

    for algorithm in algorithms:
        backends = build_demo_backends()
        balancer = LoadBalancer(backends, algorithm=algorithm)

        results = []
        for index in range(24):
            client_ip = f"172.16.0.{(index % 6) + 1}"
            request = Request(
                request_id=index,
                client_ip=client_ip,
                protocol=Protocol.TCP,
            )
            results.append(balancer.process_request(request))

        counts = Counter(
            result["backend"] for result in results if result.get("success")
        )
        print(f"{algorithm:20} {dict(counts)}")


def demonstrate_health_checks() -> None:
    print("\n=== Active health checks and failure isolation ===")

    backends = build_demo_backends()
    balancer = LoadBalancer(backends, algorithm="round_robin")

    print("Initial health:")
    for result in balancer.run_health_checks():
        print(result)

    # Simulate a backend failure. A real load balancer could observe a failed
    # HTTP /health endpoint or failed TCP connection instead.
    backends[1].metadata["health"] = "failed"

    print("\nAfter web-02 health failure:")
    for result in balancer.run_health_checks():
        print(result)

    for index in range(6):
        request = Request(
            request_id=200 + index,
            client_ip=f"192.0.2.{index + 1}",
            protocol=Protocol.TCP,
        )
        print(balancer.process_request(request))

    print("\nRestoring web-02:")
    backends[1].metadata["health"] = "ok"
    for result in balancer.run_health_checks():
        print(result)


def demonstrate_sticky_sessions() -> None:
    print("\n=== Sticky sessions ===")

    backends = build_demo_backends()
    balancer = LoadBalancer(backends, algorithm="sticky")

    session_requests = [
        Request(
            request_id=300 + index,
            client_ip="203.0.113.10",
            protocol=Protocol.HTTP,
            path="/checkout",
            session_id="session-A",
        )
        for index in range(5)
    ]

    for request in session_requests:
        print(balancer.process_request(request))

    # The session should remain on its original backend while that backend
    # remains healthy and able to accept traffic.
    original_backend = balancer.sticky.session_map["session-A"]
    print("Session affinity:", original_backend)

    # Failure forces the session mapping to recover to another backend.
    failed = balancer._find_backend(original_backend)
    failed.metadata["health"] = "failed"
    balancer.run_health_checks()

    recovery_request = Request(
        request_id=306,
        client_ip="203.0.113.10",
        protocol=Protocol.HTTP,
        path="/checkout",
        session_id="session-A",
    )

    print("After original backend failure:")
    print(balancer.process_request(recovery_request))
    print("Updated session mapping:", balancer.sticky.session_map["session-A"])


def demonstrate_capacity_limits() -> None:
    print("\n=== Backend capacity and overload ===")

    backend = BackendServer(
        backend_id="limited-01",
        host="10.0.2.10",
        port=8080,
        max_connections=2,
    )

    # Manually occupy the connection slots to demonstrate the distinction
    # between a healthy backend and an unavailable backend.
    assert backend.begin_request()
    assert backend.begin_request()

    balancer = LoadBalancer([backend], algorithm="round_robin")
    request = Request(400, "198.51.100.20", Protocol.TCP)

    result = balancer.process_request(request)
    print("Request while capacity is exhausted:", result)

    backend.finish_request()
    backend.finish_request()

    result = balancer.process_request(
        Request(401, "198.51.100.20", Protocol.TCP)
    )
    print("Request after capacity is released:", result)


def demonstrate_weighted_routing() -> None:
    print("\n=== Weighted distribution ===")

    backends = build_demo_backends()
    balancer = LoadBalancer(backends, algorithm="weighted")

    for index in range(60):
        balancer.process_request(
            Request(
                request_id=500 + index,
                client_ip=f"10.20.0.{index + 1}",
                protocol=Protocol.TCP,
            )
        )

    print("Configured weights:")
    for backend in backends:
        print(
            f"  {backend.backend_id}: weight={backend.weight}, "
            f"requests={backend.total_requests}"
        )

    print(
        "Weights express relative traffic preference. They do not by "
        "themselves guarantee identical response latency or capacity."
    )


def demonstrate_failure_modes() -> None:
    print("\n=== Failure modes and operational behavior ===")

    backends = build_demo_backends()
    balancer = LoadBalancer(backends, algorithm="round_robin")

    # Application failure and health failure are different events. A backend
    # may still accept a TCP connection while its application is returning
    # errors. Production monitoring usually needs both availability signals.
    backends[0].metadata["application_status"] = "failed"

    request = Request(600, "203.0.113.55", Protocol.HTTP, "/api/orders")
    print("Application failure:", balancer.process_request(request))

    backends[0].metadata["health"] = "failed"
    balancer.run_health_checks()

    print("After health failure:", balancer.process_request(
        Request(601, "203.0.113.55", Protocol.HTTP, "/api/orders")
    ))

    print("Metrics:", balancer.metrics())


def main() -> None:
    random.seed(42)

    demonstrate_layer4()
    demonstrate_layer7()
    demonstrate_algorithms()
    demonstrate_health_checks()
    demonstrate_sticky_sessions()
    demonstrate_capacity_limits()
    demonstrate_weighted_routing()
    demonstrate_failure_modes()

    print("\n=== Operational observations ===")
    print(
        "Layer 4 decisions are based on transport-level information, while "
        "Layer 7 decisions can use application metadata such as HTTP paths."
    )
    print(
        "Health checks remove failed backends from the eligible pool, but "
        "health-check design determines how quickly failures are detected."
    )
    print(
        "Sticky sessions preserve state locality but can create uneven load "
        "and make backend failure recovery more complex."
    )


if __name__ == "__main__":
    main()
