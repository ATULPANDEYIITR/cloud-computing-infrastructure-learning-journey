#!/usr/bin/env python3
"""
Docker Fundamentals: Architecture, Images, Containers and Registries.

A self-contained Docker environment simulator demonstrating:
- Docker client, daemon and container runtime responsibilities
- Image layers, tags, IDs and registries
- Container creation, starting, stopping and removal
- Image pulling, pushing and tagging
- Container-to-image relationships
- Resource constraints and port conflicts
- Image inspection and container logs
- Event tracking, persistence and validation

Uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import uuid

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("docker-fundamentals")


class DockerError(Exception):
    """Base exception for Docker simulation errors."""


class ValidationError(DockerError):
    pass


class ResourceError(DockerError):
    pass


class NotFoundError(DockerError):
    pass


class ConflictError(DockerError):
    pass


class ContainerStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    REMOVED = "removed"


class RuntimeState(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ImageLayer:
    digest: str
    size_mb: float
    instruction: str


@dataclass
class Image:
    image_id: str
    repository: str
    tag: str
    layers: list[ImageLayer]
    created_at: str
    architecture: str = "amd64"
    environment: dict[str, str] = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return f"{self.repository}:{self.tag}"

    @property
    def size_mb(self) -> float:
        return sum(layer.size_mb for layer in self.layers)


@dataclass
class Container:
    container_id: str
    name: str
    image_id: str
    status: ContainerStatus
    created_at: str
    ports: dict[int, int] = field(default_factory=dict)
    environment: dict[str, str] = field(default_factory=dict)
    memory_limit_mb: int = 512
    cpu_limit: float = 1.0
    logs: list[str] = field(default_factory=list)


@dataclass
class Registry:
    name: str
    images: dict[str, str] = field(default_factory=dict)
    authenticated_users: set[str] = field(default_factory=set)

    def store(self, image: Image) -> None:
        self.images[image.full_name] = image.image_id

    def resolve(self, reference: str) -> str | None:
        return self.images.get(reference)


class DockerDaemon:
    """
    Simulates the Docker daemon.

    The daemon manages images, containers, resources and lifecycle
    operations. The client does not directly manage containers.
    """

    def __init__(
        self,
        memory_capacity_mb: int = 8192,
        cpu_capacity: float = 8.0,
        storage_capacity_mb: float = 20000,
    ):
        self.memory_capacity_mb = memory_capacity_mb
        self.cpu_capacity = cpu_capacity
        self.storage_capacity_mb = storage_capacity_mb

        self.images: dict[str, Image] = {}
        self.image_tags: dict[str, str] = {}
        self.containers: dict[str, Container] = {}
        self.registries: dict[str, Registry] = {}

        self.runtime_state = RuntimeState.AVAILABLE
        self.events: list[dict[str, Any]] = []
        self.used_ports: dict[int, str] = {}

    def _event(self, action: str, resource_id: str, details: str = "") -> None:
        self.events.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "resource_id": resource_id,
            "details": details,
        })

    def _require_runtime(self) -> None:
        if self.runtime_state != RuntimeState.AVAILABLE:
            raise DockerError("Docker daemon is unavailable.")

    @staticmethod
    def _validate_reference(reference: str) -> tuple[str, str]:
        if not reference or not isinstance(reference, str):
            raise ValidationError("Image reference cannot be empty.")

        if " " in reference or reference.startswith("-"):
            raise ValidationError("Invalid image reference.")

        if reference.count(":") > 1:
            raise ValidationError("Invalid image reference.")

        repository, separator, tag = reference.rpartition(":")
        if not separator:
            repository, tag = reference, "latest"

        if not re.fullmatch(r"[a-zA-Z0-9._/-]+", repository):
            raise ValidationError("Invalid repository name.")

        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", tag):
            raise ValidationError("Invalid image tag.")

        return repository, tag

    @staticmethod
    def _digest(instruction: str) -> str:
        return "sha256:" + hashlib.sha256(
            instruction.encode("utf-8")
        ).hexdigest()

    def build_image(
        self,
        repository: str,
        tag: str,
        instructions: list[str],
        environment: dict[str, str] | None = None,
    ) -> Image:
        self._require_runtime()

        repository, validated_tag = self._validate_reference(
            f"{repository}:{tag}"
        )

        if not instructions:
            raise ValidationError("An image requires at least one layer.")

        layers = []

        for instruction in instructions:
            if not instruction.strip():
                raise ValidationError("Empty layer instruction.")

            digest = self._digest(instruction)
            size = max(0.1, len(instruction.encode("utf-8")) / 1024)

            layers.append(ImageLayer(
                digest=digest,
                size_mb=size,
                instruction=instruction,
            ))

        image = Image(
            image_id="sha256:" + hashlib.sha256(
                "".join(layer.digest for layer in layers).encode()
            ).hexdigest(),
            repository=repository,
            tag=validated_tag,
            layers=layers,
            created_at=datetime.now(timezone.utc).isoformat(),
            environment=dict(environment or {}),
        )

        existing = self.image_tags.get(image.full_name)

        if existing:
            self.image_tags.pop(image.full_name)

        self.images[image.image_id] = image
        self.image_tags[image.full_name] = image.image_id

        self._event("image_build", image.image_id, image.full_name)
        return image

    def get_image(self, reference: str) -> Image:
        self._require_runtime()

        image_id = self.image_tags.get(reference, reference)

        image = self.images.get(image_id)

        if image is None:
            raise NotFoundError(f"Image not found: {reference}")

        return image

    def tag_image(self, source: str, target: str) -> None:
        self._require_runtime()

        image = self.get_image(source)
        repository, tag = self._validate_reference(target)

        image_reference = f"{repository}:{tag}"
        self.image_tags[image_reference] = image.image_id

        self._event("image_tag", image.image_id, image_reference)

    def register_registry(self, name: str) -> Registry:
        if not name.strip():
            raise ValidationError("Registry name is required.")

        registry = Registry(name=name)
        self.registries[name] = registry
        return registry

    def push_image(
        self,
        image_reference: str,
        registry_name: str,
        username: str,
    ) -> None:
        self._require_runtime()

        image = self.get_image(image_reference)
        registry = self.registries.get(registry_name)

        if registry is None:
            raise NotFoundError("Registry does not exist.")

        if username not in registry.authenticated_users:
            raise DockerError("Registry authentication required.")

        registry.store(image)
        self._event("image_push", image.image_id, registry_name)

    def pull_image(
        self,
        registry_name: str,
        image_reference: str,
    ) -> Image:
        self._require_runtime()

        registry = self.registries.get(registry_name)

        if registry is None:
            raise NotFoundError("Registry not found.")

        image_id = registry.resolve(image_reference)

        if image_id is None:
            raise NotFoundError(
                f"Image unavailable in registry: {image_reference}"
            )

        image = self.images.get(image_id)

        if image is None:
            raise NotFoundError(
                "Registry references an image not available to this simulator."
            )

        self.image_tags[image.full_name] = image.image_id

        self._event("image_pull", image.image_id, registry_name)
        return image

    def create_container(
        self,
        name: str,
        image_reference: str,
        ports: dict[int, int] | None = None,
        environment: dict[str, str] | None = None,
        memory_limit_mb: int = 512,
        cpu_limit: float = 1.0,
    ) -> Container:
        self._require_runtime()

        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", name):
            raise ValidationError("Invalid container name.")

        if any(c.name == name and c.status != ContainerStatus.REMOVED
               for c in self.containers.values()):
            raise ConflictError("Container name already exists.")

        image = self.get_image(image_reference)

        if memory_limit_mb <= 0 or memory_limit_mb > self.memory_capacity_mb:
            raise ResourceError("Invalid memory allocation.")

        if cpu_limit <= 0 or cpu_limit > self.cpu_capacity:
            raise ResourceError("Invalid CPU allocation.")

        port_mapping = dict(ports or {})

        for host_port, container_port in port_mapping.items():
            if not (1 <= host_port <= 65535):
                raise ValidationError("Invalid host port.")

            if not (1 <= container_port <= 65535):
                raise ValidationError("Invalid container port.")

            if host_port in self.used_ports:
                raise ConflictError(f"Host port {host_port} is occupied.")

        container = Container(
            container_id=uuid.uuid4().hex[:12],
            name=name,
            image_id=image.image_id,
            status=ContainerStatus.CREATED,
            created_at=datetime.now(timezone.utc).isoformat(),
            ports=port_mapping,
            environment=dict(environment or {}),
            memory_limit_mb=memory_limit_mb,
            cpu_limit=cpu_limit,
        )

        self.containers[container.container_id] = container

        self._event(
            "container_create",
            container.container_id,
            image.full_name,
        )

        return container

    def start_container(self, container_id: str) -> Container:
        self._require_runtime()

        container = self._get_container(container_id)

        if container.status == ContainerStatus.RUNNING:
            raise ConflictError("Container is already running.")

        if container.status == ContainerStatus.REMOVED:
            raise ConflictError("Removed containers cannot be started.")

        for host_port in container.ports:
            owner = self.used_ports.get(host_port)

            if owner is not None and owner != container_id:
                raise ConflictError(f"Port {host_port} conflict.")

        container.status = ContainerStatus.RUNNING

        for host_port in container.ports:
            self.used_ports[host_port] = container_id

        container.logs.append("Container started successfully.")

        self._event("container_start", container_id)
        return container

    def stop_container(self, container_id: str) -> Container:
        self._require_runtime()

        container = self._get_container(container_id)

        if container.status != ContainerStatus.RUNNING:
            raise ConflictError("Only running containers can be stopped.")

        container.status = ContainerStatus.STOPPED

        for host_port in container.ports:
            if self.used_ports.get(host_port) == container_id:
                del self.used_ports[host_port]

        container.logs.append("Container stopped.")

        self._event("container_stop", container_id)
        return container

    def remove_container(self, container_id: str) -> None:
        self._require_runtime()

        container = self._get_container(container_id)

        if container.status == ContainerStatus.RUNNING:
            raise ConflictError("Stop the container before removal.")

        container.status = ContainerStatus.REMOVED

        self._event("container_remove", container_id)

    def _get_container(self, container_id: str) -> Container:
        container = self.containers.get(container_id)

        if container is None:
            raise NotFoundError("Container does not exist.")

        return container

    def list_containers(
        self,
        running_only: bool = False,
    ) -> list[Container]:
        result = list(self.containers.values())

        if running_only:
            result = [
                c for c in result
                if c.status == ContainerStatus.RUNNING
            ]

        return [
            c for c in result
            if c.status != ContainerStatus.REMOVED
        ]

    def remove_unused_images(self) -> int:
        self._require_runtime()

        referenced = {
            c.image_id
            for c in self.containers.values()
            if c.status != ContainerStatus.REMOVED
        }

        removed = 0

        for image_id in list(self.images):
            if image_id not in referenced:
                del self.images[image_id]

                for tag, tagged_id in list(self.image_tags.items()):
                    if tagged_id == image_id:
                        del self.image_tags[tag]

                removed += 1
                self._event("image_remove", image_id)

        return removed

    def inspect_image(self, reference: str) -> dict[str, Any]:
        image = self.get_image(reference)

        return {
            "id": image.image_id,
            "reference": image.full_name,
            "architecture": image.architecture,
            "size_mb": round(image.size_mb, 4),
            "layers": [asdict(layer) for layer in image.layers],
            "environment": image.environment,
        }

    def save_state(self, path: Path) -> None:
        """Persist a safe inventory snapshot, not a live daemon backup."""
        data = {
            "images": [
                {
                    "id": image.image_id,
                    "reference": image.full_name,
                    "size_mb": image.size_mb,
                }
                for image in self.images.values()
            ],
            "containers": [
                {
                    "id": c.container_id,
                    "name": c.name,
                    "image_id": c.image_id,
                    "status": c.status.value,
                    "ports": c.ports,
                }
                for c in self.containers.values()
            ],
            "events": self.events,
        }

        temporary = path.with_suffix(path.suffix + ".tmp")

        temporary.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8",
        )

        temporary.replace(path)


class DockerClient:
    """
    Simulates the Docker CLI/API client.

    Requests are forwarded to the daemon, which owns runtime state.
    """

    def __init__(self, daemon: DockerDaemon):
        self.daemon = daemon

    def run(self, name: str, image: str, **kwargs: Any) -> Container:
        container = self.daemon.create_container(
            name=name,
            image_reference=image,
            **kwargs,
        )
        return self.daemon.start_container(container.container_id)

    def ps(self) -> None:
        print("\nCONTAINER INVENTORY")
        print("-" * 90)

        for container in self.daemon.list_containers():
            print(
                f"{container.container_id:12} "
                f"{container.name:18} "
                f"{container.status.value:10} "
                f"{container.image_id[:19]}"
            )

    def images(self) -> None:
        print("\nIMAGE INVENTORY")
        print("-" * 75)

        for reference, image_id in sorted(
            self.daemon.image_tags.items()
        ):
            image = self.daemon.images.get(image_id)

            if image:
                print(
                    f"{reference:35} "
                    f"{image_id[:20]} "
                    f"{image.size_mb:.4f} MB"
                )


def demonstrate() -> None:
    print("=" * 72)
    print("DOCKER FUNDAMENTALS SIMULATOR")
    print("=" * 72)

    daemon = DockerDaemon(
        memory_capacity_mb=4096,
        cpu_capacity=4.0,
    )

    client = DockerClient(daemon)

    registry = daemon.register_registry("registry.example.com")
    registry.authenticated_users.add("developer")

    # Simulate image construction from ordered filesystem layers.
    image = daemon.build_image(
        repository="demo/web-app",
        tag="1.0",
        instructions=[
            "FROM python:3.13-slim",
            "WORKDIR /app",
            "COPY requirements.txt .",
            "RUN pip install flask",
            "COPY application.py .",
            "CMD python application.py",
        ],
        environment={
            "APP_ENV": "production",
            "PORT": "8080",
        },
    )

    print("\n1. IMAGE INSPECTION")
    print(json.dumps(
        daemon.inspect_image(image.full_name),
        indent=2,
    ))

    print("\n2. REGISTRY PUSH")
    daemon.push_image(
        image.full_name,
        "registry.example.com",
        "developer",
    )
    print("Image pushed successfully.")

    print("\n3. CONTAINER CREATION AND START")
    container = client.run(
        name="web-container",
        image=image.full_name,
        ports={8080: 8080},
        environment={"APP_ENV": "production"},
        memory_limit_mb=512,
        cpu_limit=1.0,
    )

    print(f"Container ID: {container.container_id}")
    print(f"Status: {container.status.value}")

    print("\n4. CONTAINER INVENTORY")
    client.ps()

    print("\n5. EDGE CASE: PORT CONFLICT")

    try:
        client.run(
            name="conflicting-container",
            image=image.full_name,
            ports={8080: 9000},
        )
    except DockerError as exc:
        print(f"Expected failure: {exc}")

    print("\n6. CONTAINER STOP")

    daemon.stop_container(container.container_id)
    print("Container stopped.")

    print("\n7. CONTAINER RESTART")

    daemon.start_container(container.container_id)
    print("Container restarted.")

    print("\n8. CONTAINER REMOVAL")

    daemon.stop_container(container.container_id)
    daemon.remove_container(container.container_id)

    print("Container removed.")

    print("\n9. IMAGE TAGGING")

    daemon.tag_image(
        image.full_name,
        "demo/web-app:stable",
    )

    client.images()

    print("\n10. EVENT HISTORY")

    for event in daemon.events:
        print(
            f"{event['action']:20} "
            f"{event['resource_id'][:16]} "
            f"{event['details']}"
        )

    print("\n11. PERSISTENCE")

    output = Path("docker_inventory.json")
    daemon.save_state(output)
    print(f"Inventory saved to {output.resolve()}")

    print("\n12. VALIDATION")

    assert container.status == ContainerStatus.REMOVED
    assert "demo/web-app:stable" in daemon.image_tags
    assert len(daemon.events) >= 8

    print("All demonstration assertions passed.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Docker fundamentals simulator"
    )

    parser.add_argument(
        "--output",
        default="docker_inventory.json",
        help="Inventory snapshot output path",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress informational logging",
    )

    args = parser.parse_args()

    if args.quiet:
        logging.disable(logging.CRITICAL)

    try:
        demonstrate()
        return 0
    except (DockerError, OSError, ValueError) as exc:
        logger.error("Execution failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
