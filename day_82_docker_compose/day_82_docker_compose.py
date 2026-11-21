#!/usr/bin/env python3
"""
Docker Compose: Multi-container Application Simulator

Models:
- Services and container configuration
- Dependency ordering and health conditions
- Networks and service discovery
- Persistent and temporary volumes
- Environment configuration and validation
- Startup, failure, recovery, and shutdown
- Resource constraints and deployment reporting

Requires Python 3.10+.
Uses only the Python standard library.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s"
)
logger = logging.getLogger("compose-simulator")


class ComposeError(Exception):
    """Base exception for Compose simulation errors."""


class ConfigurationError(ComposeError):
    """Invalid service or application configuration."""


class DependencyError(ComposeError):
    """A service dependency cannot be satisfied."""


class DeploymentError(ComposeError):
    """A service cannot be deployed."""


class ServiceState(Enum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STOPPED = "stopped"
    FAILED = "failed"


class DependencyCondition(Enum):
    SERVICE_STARTED = "service_started"
    SERVICE_HEALTHY = "service_healthy"
    SERVICE_COMPLETED = "service_completed_successfully"


@dataclass(frozen=True)
class EnvironmentConfig:
    values: dict[str, str]
    required: tuple[str, ...] = ()

    def validate(self) -> None:
        missing = [
            key for key in self.required
            if not self.values.get(key)
        ]

        if missing:
            raise ConfigurationError(
                f"Missing required environment variables: {missing}"
            )

        for key, value in self.values.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                raise ConfigurationError(
                    f"Invalid environment variable name: {key}"
                )

            if "\x00" in value:
                raise ConfigurationError(
                    f"Invalid null character in {key}"
                )


@dataclass(frozen=True)
class Volume:
    name: str
    persistent: bool = True
    read_only: bool = False

    def __post_init__(self):
        if not self.name:
            raise ConfigurationError("Volume name cannot be empty.")


@dataclass(frozen=True)
class Network:
    name: str
    internal: bool = False

    def __post_init__(self):
        if not self.name:
            raise ConfigurationError("Network name cannot be empty.")


@dataclass(frozen=True)
class Dependency:
    service: str
    condition: DependencyCondition = (
        DependencyCondition.SERVICE_STARTED
    )


@dataclass
class Service:
    name: str
    image: str
    dependencies: list[Dependency] = field(default_factory=list)
    networks: set[str] = field(default_factory=set)
    volumes: list[Volume] = field(default_factory=list)
    environment: EnvironmentConfig = field(
        default_factory=lambda: EnvironmentConfig({})
    )
    ports: list[tuple[int, int]] = field(default_factory=list)
    memory_limit_mb: int = 256
    cpu_limit: float = 1.0
    healthcheck_enabled: bool = False
    state: ServiceState = ServiceState.CREATED
    restart_policy: str = "no"
    restart_count: int = 0

    def validate(self) -> None:
        if not self.name:
            raise ConfigurationError("Service name is required.")

        if not self.image or any(c.isspace() for c in self.image):
            raise ConfigurationError(
                f"Invalid image reference for {self.name}"
            )

        if self.memory_limit_mb <= 0:
            raise ConfigurationError("Memory limit must be positive.")

        if not 0 < self.cpu_limit <= 128:
            raise ConfigurationError("Invalid CPU limit.")

        if self.restart_policy not in {
            "no", "always", "unless-stopped", "on-failure"
        }:
            raise ConfigurationError("Invalid restart policy.")

        self.environment.validate()

        for host_port, container_port in self.ports:
            if not (
                1 <= host_port <= 65535
                and 1 <= container_port <= 65535
            ):
                raise ConfigurationError(
                    f"Invalid port mapping in {self.name}"
                )


@dataclass
class Deployment:
    services: dict[str, Service]
    networks: dict[str, Network]
    volumes: dict[str, Volume]

    def validate(self) -> None:
        if not self.services:
            raise ConfigurationError("At least one service is required.")

        host_ports: dict[int, str] = {}

        for name, service in self.services.items():
            if name != service.name:
                raise ConfigurationError(
                    f"Service key mismatch: {name}"
                )

            service.validate()

            for network_name in service.networks:
                if network_name not in self.networks:
                    raise ConfigurationError(
                        f"{name} references unknown network "
                        f"{network_name}"
                    )

            for volume in service.volumes:
                if volume.name not in self.volumes:
                    raise ConfigurationError(
                        f"{name} references unknown volume "
                        f"{volume.name}"
                    )

            for dependency in service.dependencies:
                if dependency.service not in self.services:
                    raise DependencyError(
                        f"{name} depends on missing service "
                        f"{dependency.service}"
                    )

                if dependency.service == name:
                    raise DependencyError(
                        f"{name} cannot depend on itself"
                    )

            for host_port, _ in service.ports:
                if host_port in host_ports:
                    raise ConfigurationError(
                        f"Host port {host_port} is already assigned "
                        f"to {host_ports[host_port]}"
                    )

                host_ports[host_port] = name

        self.topological_order()

    def topological_order(self) -> list[str]:
        """Return dependency-first service startup order."""

        visited: set[str] = set()
        active: set[str] = set()
        result: list[str] = []

        def visit(name: str) -> None:
            if name in active:
                raise DependencyError(
                    f"Circular dependency detected at {name}"
                )

            if name in visited:
                return

            active.add(name)

            for dependency in self.services[name].dependencies:
                visit(dependency.service)

            active.remove(name)
            visited.add(name)
            result.append(name)

        for name in sorted(self.services):
            visit(name)

        return result


class ComposeSimulator:
    def __init__(self, deployment: Deployment):
        deployment.validate()
        self.deployment = deployment
        self.events: list[dict] = []

    def record(self, event: str, service: str, details: str = "") -> None:
        self.events.append({
            "event": event,
            "service": service,
            "details": details
        })

        logger.info("%s: %s %s", event, service, details)

    def dependency_satisfied(self, dependency: Dependency) -> bool:
        state = self.deployment.services[
            dependency.service
        ].state

        if dependency.condition == DependencyCondition.SERVICE_STARTED:
            return state in {
                ServiceState.RUNNING,
                ServiceState.HEALTHY
            }

        if dependency.condition == DependencyCondition.SERVICE_HEALTHY:
            return state == ServiceState.HEALTHY

        if dependency.condition == (
            DependencyCondition.SERVICE_COMPLETED
        ):
            return state == ServiceState.STOPPED

        return False

    def start_service(self, name: str) -> None:
        service = self.deployment.services[name]

        if service.state in {
            ServiceState.RUNNING,
            ServiceState.HEALTHY
        }:
            return

        for dependency in service.dependencies:
            if not self.dependency_satisfied(dependency):
                raise DependencyError(
                    f"{name} cannot start: dependency "
                    f"{dependency.service} does not satisfy "
                    f"{dependency.condition.value}"
                )

        service.state = ServiceState.STARTING
        self.record("STARTING", name, service.image)

        service.state = ServiceState.RUNNING
        self.record("RUNNING", name)

        if service.healthcheck_enabled:
            self.healthcheck(name)

    def healthcheck(
        self,
        name: str,
        success: bool = True
    ) -> bool:
        service = self.deployment.services[name]

        if service.state not in {
            ServiceState.RUNNING,
            ServiceState.HEALTHY,
            ServiceState.UNHEALTHY
        }:
            raise DeploymentError(
                f"Cannot healthcheck {name} in state {service.state.value}"
            )

        service.state = (
            ServiceState.HEALTHY
            if success
            else ServiceState.UNHEALTHY
        )

        self.record(
            "HEALTHCHECK",
            name,
            service.state.value
        )

        return success

    def up(self) -> list[str]:
        """Start services in dependency order."""

        order = self.deployment.topological_order()

        for name in order:
            self.start_service(name)

        return order

    def fail_service(self, name: str) -> None:
        service = self.deployment.services[name]
        service.state = ServiceState.FAILED
        self.record("FAILED", name)

    def restart_service(self, name: str) -> None:
        service = self.deployment.services[name]

        if service.restart_policy == "no":
            raise DeploymentError(
                f"Automatic restart disabled for {name}"
            )

        service.restart_count += 1
        service.state = ServiceState.CREATED

        self.record(
            "RESTART",
            name,
            f"attempt={service.restart_count}"
        )

        self.start_service(name)

    def down(self, remove_volumes: bool = False) -> None:
        """Stop services in reverse dependency order."""

        for name in reversed(
            self.deployment.topological_order()
        ):
            service = self.deployment.services[name]

            if service.state != ServiceState.STOPPED:
                service.state = ServiceState.STOPPED
                self.record("STOPPED", name)

        if remove_volumes:
            for volume in self.deployment.volumes.values():
                if volume.persistent:
                    logger.warning(
                        "Persistent volume %s requires explicit "
                        "data-removal handling.",
                        volume.name
                    )

                else:
                    self.record(
                        "VOLUME_REMOVED",
                        volume.name
                    )

    def network_peers(self, service_name: str) -> list[str]:
        service = self.deployment.services[service_name]

        return sorted(
            other.name
            for other in self.deployment.services.values()
            if other.name != service_name
            and service.networks.intersection(other.networks)
        )

    def report(self) -> dict:
        return {
            "services": {
                name: {
                    "image": service.image,
                    "state": service.state.value,
                    "restart_count": service.restart_count,
                    "networks": sorted(service.networks),
                    "memory_limit_mb": service.memory_limit_mb
                }
                for name, service in self.deployment.services.items()
            },
            "events": self.events
        }


def build_application() -> Deployment:
    """Define an API, database, and frontend application."""

    networks = {
        "frontend": Network("frontend"),
        "backend": Network("backend", internal=True)
    }

    volumes = {
        "postgres_data": Volume("postgres_data"),
        "cache_data": Volume("cache_data")
    }

    services = {
        "database": Service(
            name="database",
            image="postgres:18",
            networks={"backend"},
            volumes=[Volume("postgres_data")],
            environment=EnvironmentConfig(
                {
                    "POSTGRES_DB": "application",
                    "POSTGRES_USER": "appuser",
                    "POSTGRES_PASSWORD": "local-development-password"
                },
                required=(
                    "POSTGRES_DB",
                    "POSTGRES_USER",
                    "POSTGRES_PASSWORD"
                )
            ),
            memory_limit_mb=1024,
            healthcheck_enabled=True,
            restart_policy="unless-stopped"
        ),

        "cache": Service(
            name="cache",
            image="redis:7-alpine",
            networks={"backend"},
            volumes=[Volume("cache_data")],
            memory_limit_mb=256,
            healthcheck_enabled=True,
            restart_policy="unless-stopped"
        ),

        "api": Service(
            name="api",
            image="example/api:1.0",
            dependencies=[
                Dependency(
                    "database",
                    DependencyCondition.SERVICE_HEALTHY
                ),
                Dependency(
                    "cache",
                    DependencyCondition.SERVICE_STARTED
                )
            ],
            networks={"frontend", "backend"},
            ports=[(8080, 8080)],
            environment=EnvironmentConfig(
                {
                    "DATABASE_HOST": "database",
                    "DATABASE_PORT": "5432",
                    "CACHE_HOST": "cache",
                    "CACHE_PORT": "6379"
                }
            ),
            memory_limit_mb=512,
            healthcheck_enabled=True,
            restart_policy="on-failure"
        ),

        "web": Service(
            name="web",
            image="example/web:1.0",
            dependencies=[
                Dependency(
                    "api",
                    DependencyCondition.SERVICE_HEALTHY
                )
            ],
            networks={"frontend"},
            ports=[(3000, 3000)],
            environment=EnvironmentConfig({
                "API_BASE_URL": "http://api:8080"
            }),
            memory_limit_mb=256,
            restart_policy="unless-stopped"
        )
    }

    return Deployment(
        services=services,
        networks=networks,
        volumes=volumes
    )


def main() -> int:
    try:
        deployment = build_application()
        simulator = ComposeSimulator(deployment)

        print("\nSTARTUP ORDER")
        order = simulator.up()

        for index, name in enumerate(order, start=1):
            print(f"{index}. {name}")

        print("\nNETWORK DISCOVERY")
        for name in deployment.services:
            print(
                f"{name}: "
                f"{simulator.network_peers(name)}"
            )

        print("\nFAILURE AND RECOVERY")
        simulator.fail_service("api")
        simulator.restart_service("api")

        print("\nDEPLOYMENT REPORT")
        print(json.dumps(
            simulator.report(),
            indent=2
        ))

        print("\nSHUTDOWN")
        simulator.down()

        return 0

    except ComposeError as exc:
        logger.error("Deployment error: %s", exc)
        return 1

    except Exception:
        logger.exception("Unexpected application failure")
        return 2


if __name__ == "__main__":
    sys.exit(main())
