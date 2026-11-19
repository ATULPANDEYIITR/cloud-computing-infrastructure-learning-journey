#!/usr/bin/env python3
"""
Docker Networking: Bridge Networks, Host Networking and Container Communication

Python 3.10+
Standard library only.

Demonstrates:
- Docker network architecture
- Bridge and host network drivers
- Custom bridge networks
- Container IP allocation
- DNS-based service discovery
- Container-to-container communication
- Port publishing and port mapping
- Network isolation
- Network attachment and detachment
- Network inspection
- Firewall-like connectivity rules
- Subnet and IP validation
- Network failure handling
- Automated tests
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from ipaddress import IPv4Address, IPv4Network, ip_address, ip_network
from typing import Optional
import json
import logging


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)
logger = logging.getLogger("docker-networking")


class NetworkError(Exception):
    pass


class ValidationError(NetworkError):
    pass


class AddressConflictError(NetworkError):
    pass


class ConnectivityError(NetworkError):
    pass


class NetworkDriver(Enum):
    BRIDGE = "bridge"
    HOST = "host"


@dataclass(frozen=True)
class PortBinding:
    container_port: int
    host_port: int
    protocol: str = "tcp"

    def __post_init__(self):
        if not 1 <= self.container_port <= 65535:
            raise ValidationError("Invalid container port.")
        if not 1 <= self.host_port <= 65535:
            raise ValidationError("Invalid host port.")
        if self.protocol.lower() not in {"tcp", "udp"}:
            raise ValidationError("Unsupported transport protocol.")


@dataclass
class Container:
    name: str
    image: str
    ports: dict[int, str] = field(default_factory=dict)
    network_ids: set[str] = field(default_factory=set)
    addresses: dict[str, str] = field(default_factory=dict)
    running: bool = True

    def __post_init__(self):
        if not self.name or not self.image:
            raise ValidationError("Container name and image are required.")

        for port, protocol in self.ports.items():
            if not 1 <= port <= 65535:
                raise ValidationError("Invalid container port.")
            if protocol.lower() not in {"tcp", "udp"}:
                raise ValidationError("Invalid protocol.")


@dataclass
class DockerNetwork:
    name: str
    driver: NetworkDriver
    subnet: Optional[IPv4Network] = None
    gateway: Optional[IPv4Address] = None
    containers: dict[str, Container] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    next_host: int = 2
    id: str = ""

    def __post_init__(self):
        if not self.name:
            raise ValidationError("Network name is required.")

        if self.driver == NetworkDriver.BRIDGE:
            if self.subnet is None:
                raise ValidationError(
                    "Bridge networks require a subnet."
                )

            if self.subnet.version != 4 or self.subnet.num_addresses < 4:
                raise ValidationError("Invalid bridge subnet.")

            if self.gateway is None:
                self.gateway = IPv4Address(
                    int(self.subnet.network_address) + 1
                )

            if self.gateway not in self.subnet:
                raise ValidationError("Gateway must belong to subnet.")

        elif self.subnet is not None:
            raise ValidationError(
                "Host networks do not use isolated bridge subnets."
            )


class DockerHost:
    """
    Simulates a Docker host and its network management operations.

    Bridge networks have independent IP address spaces.
    Host networking shares the host network namespace.
    """

    def __init__(self, hostname: str = "docker-host"):
        self.hostname = hostname
        self.networks: dict[str, DockerNetwork] = {}
        self.containers: dict[str, Container] = {}
        self.bindings: dict[tuple[int, str], str] = {}
        self.host_ports: dict[int, str] = {}
        self.events: list[dict] = []

    def event(self, operation: str, message: str):
        self.events.append({
            "operation": operation,
            "message": message
        })
        logger.info("%s: %s", operation, message)

    def create_network(
        self,
        name: str,
        driver: str = "bridge",
        subnet: str = "172.20.0.0/24"
    ) -> DockerNetwork:

        if name in self.networks:
            raise ValidationError("Network already exists.")

        try:
            network_driver = NetworkDriver(driver)
        except ValueError as exc:
            raise ValidationError("Unsupported network driver.") from exc

        parsed_subnet = (
            ip_network(subnet, strict=True)
            if network_driver == NetworkDriver.BRIDGE
            else None
        )

        network = DockerNetwork(
            name=name,
            driver=network_driver,
            subnet=parsed_subnet,
            id=f"net-{len(self.networks) + 1:04d}"
        )

        if parsed_subnet:
            for existing in self.networks.values():
                if (
                    existing.subnet
                    and parsed_subnet.overlaps(existing.subnet)
                ):
                    raise AddressConflictError(
                        f"Subnet overlaps {existing.name}."
                    )

        self.networks[name] = network
        self.event("NetworkCreated", name)
        return network

    def create_container(
        self,
        name: str,
        image: str,
        ports: Optional[dict[int, str]] = None
    ) -> Container:

        if name in self.containers:
            raise ValidationError("Container already exists.")

        container = Container(
            name=name,
            image=image,
            ports=ports or {}
        )

        self.containers[name] = container
        self.event("ContainerCreated", name)
        return container

    def _allocate_ip(self, network: DockerNetwork) -> str:
        if network.subnet is None:
            raise ValidationError("Network has no IP subnet.")

        while network.next_host < network.subnet.num_addresses - 1:
            candidate = IPv4Address(
                int(network.subnet.network_address)
                + network.next_host
            )
            network.next_host += 1

            if candidate != network.gateway:
                return str(candidate)

        raise AddressConflictError(
            f"No available IP addresses in {network.name}."
        )

    def connect(
        self,
        container_name: str,
        network_name: str,
        aliases: Optional[list[str]] = None
    ):
        container = self.containers[container_name]
        network = self.networks[network_name]

        if not container.running:
            raise NetworkError("Cannot connect a stopped container.")

        if network.driver == NetworkDriver.HOST:
            container.network_ids.add(network.id)
            self.event(
                "NetworkConnected",
                f"{container_name} -> host"
            )
            return

        if network.id in container.network_ids:
            raise ValidationError("Container is already connected.")

        address = self._allocate_ip(network)

        network.containers[container.name] = container
        container.network_ids.add(network.id)
        container.addresses[network.id] = address

        network.aliases[container.name] = container.name

        for alias in aliases or []:
            if not alias:
                raise ValidationError("Aliases cannot be empty.")

            owner = network.aliases.get(alias)

            if owner and owner != container.name:
                raise ValidationError(
                    f"Alias {alias} is already assigned."
                )

            network.aliases[alias] = container.name

        self.event(
            "NetworkConnected",
            f"{container_name} -> {network_name} ({address})"
        )

    def disconnect(self, container_name: str, network_name: str):
        container = self.containers[container_name]
        network = self.networks[network_name]

        if network.driver == NetworkDriver.HOST:
            raise NetworkError(
                "Host networking cannot be disconnected independently."
            )

        if network.id not in container.network_ids:
            raise ValidationError("Container is not connected.")

        network.containers.pop(container_name)

        aliases_to_remove = [
            alias for alias, owner in network.aliases.items()
            if owner == container_name
        ]

        for alias in aliases_to_remove:
            network.aliases.pop(alias)

        container.network_ids.remove(network.id)
        container.addresses.pop(network.id)

        self.event(
            "NetworkDisconnected",
            f"{container_name} from {network_name}"
        )

    def resolve(
        self,
        source_name: str,
        destination_name: str,
        network_name: str
    ) -> str:

        source = self.containers[source_name]
        network = self.networks[network_name]

        if network.driver == NetworkDriver.HOST:
            raise ConnectivityError(
                "Host networking does not use bridge DNS."
            )

        if network.id not in source.network_ids:
            raise ConnectivityError(
                "Source container is not connected."
            )

        target_name = network.aliases.get(destination_name)

        if target_name is None:
            raise ConnectivityError(
                f"DNS name {destination_name} was not found."
            )

        return network.containers[target_name].addresses[network.id]

    def can_communicate(
        self,
        source_name: str,
        destination_name: str,
        network_name: str,
        destination_port: int
    ) -> bool:

        source = self.containers[source_name]
        destination = self.containers[destination_name]
        network = self.networks[network_name]

        if not source.running or not destination.running:
            return False

        if destination_port not in destination.ports:
            return False

        if network.driver == NetworkDriver.HOST:
            return (
                network.id in source.network_ids
                and network.id in destination.network_ids
            )

        return (
            network.id in source.network_ids
            and network.id in destination.network_ids
            and destination_name in network.containers
        )

    def publish_port(
        self,
        container_name: str,
        binding: PortBinding
    ):
        container = self.containers[container_name]

        if binding.container_port not in container.ports:
            raise ValidationError(
                "Container does not declare the destination port."
            )

        key = (binding.host_port, binding.protocol)

        if key in self.bindings:
            raise AddressConflictError(
                "Host port is already published."
            )

        if binding.host_port in self.host_ports:
            raise AddressConflictError(
                "Host port is already reserved."
            )

        self.bindings[key] = container_name
        self.host_ports[binding.host_port] = container_name

        self.event(
            "PortPublished",
            f"{binding.host_port}:{binding.container_port}"
        )

    def stop_container(self, container_name: str):
        container = self.containers[container_name]
        container.running = False

        for key in list(self.bindings):
            if self.bindings[key] == container_name:
                self.bindings.pop(key)

        for port in list(self.host_ports):
            if self.host_ports[port] == container_name:
                self.host_ports.pop(port)

        self.event("ContainerStopped", container_name)

    def start_container(self, container_name: str):
        self.containers[container_name].running = True
        self.event("ContainerStarted", container_name)

    def inspect_network(self, network_name: str) -> dict:
        network = self.networks[network_name]

        return {
            "name": network.name,
            "driver": network.driver.value,
            "subnet": str(network.subnet) if network.subnet else None,
            "gateway": str(network.gateway) if network.gateway else None,
            "containers": {
                name: container.addresses.get(network.id, "host-network")
                for name, container in network.containers.items()
            },
            "aliases": dict(network.aliases)
        }

    def report(self) -> dict:
        return {
            "hostname": self.hostname,
            "networks": {
                name: self.inspect_network(name)
                for name in self.networks
            },
            "containers": {
                name: {
                    "image": container.image,
                    "running": container.running,
                    "network_ids": sorted(container.network_ids),
                    "addresses": container.addresses
                }
                for name, container in self.containers.items()
            },
            "published_ports": {
                f"{port}/{protocol}": container
                for (port, protocol), container in self.bindings.items()
            },
            "events": self.events
        }


def run_tests():
    host = DockerHost()

    # Independent custom bridge networks.
    host.create_network(
        "frontend",
        subnet="172.20.0.0/24"
    )

    host.create_network(
        "backend",
        subnet="172.21.0.0/24"
    )

    web = host.create_container(
        "web",
        "nginx:1.27",
        {80: "tcp"}
    )

    api = host.create_container(
        "api",
        "python:3.13",
        {8000: "tcp"}
    )

    database = host.create_container(
        "database",
        "postgres:18",
        {5432: "tcp"}
    )

    host.connect("web", "frontend")
    host.connect("api", "frontend", ["api-service"])
    host.connect("api", "backend")
    host.connect("database", "backend", ["db"])

    # DNS resolution works within the shared bridge.
    api_ip = host.resolve(
        "web",
        "api-service",
        "frontend"
    )

    assert api_ip == "172.20.0.3"

    # Frontend containers can communicate.
    assert host.can_communicate(
        "web", "api", "frontend", 8000
    )

    # Isolated networks cannot communicate directly.
    assert not host.can_communicate(
        "web", "database", "frontend", 5432
    )

    assert host.can_communicate(
        "api", "database", "backend", 5432
    )

    host.publish_port(
        "web",
        PortBinding(80, 8080)
    )

    assert host.bindings[(8080, "tcp")] == "web"

    # A container can be attached to more than one network.
    assert len(api.network_ids) == 2

    # Host networking uses the host network namespace.
    host.create_network("host-mode", driver="host")
    host.connect("web", "host-mode")

    assert (
        host.networks["host-mode"].driver
        == NetworkDriver.HOST
    )

    # Stopping a container removes its published bindings.
    host.stop_container("web")
    assert (8080, "tcp") not in host.bindings

    host.start_container("web")

    # Overlapping bridge networks must be rejected.
    try:
        host.create_network(
            "conflicting",
            subnet="172.20.0.0/25"
        )
        raise AssertionError("Overlapping subnet was accepted.")
    except AddressConflictError:
        pass

    # DNS isolation must be enforced.
    try:
        host.resolve("web", "db", "frontend")
        raise AssertionError("Unexpected DNS resolution.")
    except ConnectivityError:
        pass

    print("All Docker networking tests passed.")
    print(json.dumps(host.report(), indent=2))


if __name__ == "__main__":
    run_tests()
