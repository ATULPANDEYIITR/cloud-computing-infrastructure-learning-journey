#!/usr/bin/env python3
"""
Containerization Fundamentals and Runtime Simulation

Demonstrates:
- Container images, layers, registries and image digests
- Containers, processes and lifecycle management
- Namespace and cgroup isolation concepts
- Resource limits and monitoring
- Portability and environment configuration
- Container runtime operations
- Health checks, failure handling and restart policies
- Image security and deployment validation

Uses Python standard library only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import re
import time
import uuid

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

logger = logging.getLogger("container-lab")


class ContainerError(Exception):
    """Base exception for container operations."""


class ValidationError(ContainerError):
    pass


class RuntimeError(ContainerError):
    pass


class ResourceLimitError(ContainerError):
    pass


class ImageNotFoundError(ContainerError):
    pass


class ContainerState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"
    REMOVED = "removed"


class RestartPolicy(str, Enum):
    NEVER = "never"
    ON_FAILURE = "on-failure"
    ALWAYS = "always"


class IsolationType(str, Enum):
    PROCESS = "process"
    NETWORK = "network"
    MOUNT = "mount"
    USER = "user"
    IPC = "ipc"
    UTS = "uts"


@dataclass(frozen=True)
class ResourceLimits:
    cpu_cores: float = 1.0
    memory_mb: int = 256
    disk_mb: int = 512
    process_limit: int = 64

    def __post_init__(self):
        if not 0 < self.cpu_cores <= 128:
            raise ValidationError("CPU limit must be between 0 and 128.")

        if not 16 <= self.memory_mb <= 1_048_576:
            raise ValidationError("Memory limit is invalid.")

        if not 16 <= self.disk_mb <= 10_485_760:
            raise ValidationError("Disk limit is invalid.")

        if not 1 <= self.process_limit <= 100_000:
            raise ValidationError("Process limit is invalid.")


@dataclass(frozen=True)
class ImageLayer:
    name: str
    content: str

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            self.content.encode("utf-8")
        ).hexdigest()


@dataclass
class ContainerImage:
    name: str
    version: str
    layers: list[ImageLayer]
    entrypoint: str
    exposed_ports: set[int] = field(default_factory=set)

    def __post_init__(self):
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._/-]{0,127}", self.name):
            raise ValidationError("Invalid image name.")

        if not self.version or len(self.version) > 64:
            raise ValidationError("Invalid image version.")

        if not self.layers:
            raise ValidationError("An image must contain at least one layer.")

        if not self.entrypoint.strip():
            raise ValidationError("Entrypoint cannot be empty.")

        if any(not 1 <= port <= 65535 for port in self.exposed_ports):
            raise ValidationError("Invalid exposed port.")

    @property
    def digest(self) -> str:
        layer_digests = "".join(
            layer.digest for layer in self.layers
        )

        payload = (
            self.name
            + self.version
            + self.entrypoint
            + layer_digests
        )

        return hashlib.sha256(
            payload.encode("utf-8")
        ).hexdigest()

    @property
    def reference(self) -> str:
        return f"{self.name}:{self.version}"


@dataclass
class Container:
    container_id: str
    image: ContainerImage
    name: str
    limits: ResourceLimits
    restart_policy: RestartPolicy
    environment: dict[str, str]
    isolation: set[IsolationType]

    state: ContainerState = ContainerState.CREATED
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    started_at: str | None = None
    stopped_at: str | None = None
    exit_code: int | None = None
    restart_count: int = 0

    memory_used_mb: int = 0
    cpu_used_percent: float = 0.0
    process_count: int = 0

    def metrics(self) -> dict[str, Any]:
        return {
            "id": self.container_id,
            "name": self.name,
            "state": self.state.value,
            "memory_used_mb": self.memory_used_mb,
            "memory_limit_mb": self.limits.memory_mb,
            "cpu_percent": self.cpu_used_percent,
            "process_count": self.process_count,
            "restart_count": self.restart_count
        }


class ImageRegistry:
    """In-memory image registry with immutable digest references."""

    def __init__(self):
        self.images: dict[str, ContainerImage] = {}
        self.digest_index: dict[str, ContainerImage] = {}

    def push(self, image: ContainerImage) -> None:
        self.images[image.reference] = image
        self.digest_index[image.digest] = image
        logger.info("Image registered: %s", image.reference)

    def pull(self, reference: str) -> ContainerImage:
        image = self.images.get(reference)

        if image is None:
            raise ImageNotFoundError(
                f"Image not found: {reference}"
            )

        return image

    def pull_by_digest(self, digest: str) -> ContainerImage:
        image = self.digest_index.get(digest)

        if image is None:
            raise ImageNotFoundError("Unknown image digest.")

        return image


class ContainerRuntime:
    """
    Simulated container runtime.

    This class models lifecycle and policy behavior.
    It does not create operating-system namespaces or cgroups.
    """

    def __init__(self, registry: ImageRegistry):
        self.registry = registry
        self.containers: dict[str, Container] = {}
        self.names: set[str] = set()

    def create(
        self,
        image_reference: str,
        name: str,
        limits: ResourceLimits | None = None,
        environment: dict[str, str] | None = None,
        restart_policy: RestartPolicy = RestartPolicy.NEVER
    ) -> Container:

        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}", name):
            raise ValidationError("Invalid container name.")

        if name in self.names:
            raise ValidationError("Container name already exists.")

        image = self.registry.pull(image_reference)

        environment = environment or {}

        if len(environment) > 128:
            raise ValidationError("Too many environment variables.")

        for key, value in environment.items():
            if not re.fullmatch(r"[A-Z_][A-Z0-9_]{0,63}", key):
                raise ValidationError("Invalid environment variable name.")

            if not isinstance(value, str) or len(value) > 4096:
                raise ValidationError("Invalid environment variable value.")

        container = Container(
            container_id=str(uuid.uuid4()),
            image=image,
            name=name,
            limits=limits or ResourceLimits(),
            restart_policy=restart_policy,
            environment=dict(environment),
            isolation=set(IsolationType)
        )

        self.containers[container.container_id] = container
        self.names.add(name)

        logger.info("Container created: %s", name)
        return container

    def _get(self, container_id: str) -> Container:
        try:
            return self.containers[container_id]
        except KeyError:
            raise ContainerError("Container does not exist.")

    def start(self, container_id: str) -> None:
        container = self._get(container_id)

        if container.state not in (
            ContainerState.CREATED,
            ContainerState.STOPPED
        ):
            raise RuntimeError(
                f"Cannot start container in state {container.state.value}."
            )

        container.state = ContainerState.RUNNING
        container.started_at = datetime.now(timezone.utc).isoformat()
        container.stopped_at = None
        container.exit_code = None

        logger.info("Container started: %s", container.name)

    def pause(self, container_id: str) -> None:
        container = self._get(container_id)

        if container.state != ContainerState.RUNNING:
            raise RuntimeError("Only running containers can be paused.")

        container.state = ContainerState.PAUSED

    def unpause(self, container_id: str) -> None:
        container = self._get(container_id)

        if container.state != ContainerState.PAUSED:
            raise RuntimeError("Container is not paused.")

        container.state = ContainerState.RUNNING

    def stop(self, container_id: str, exit_code: int = 0) -> None:
        container = self._get(container_id)

        if container.state not in (
            ContainerState.RUNNING,
            ContainerState.PAUSED
        ):
            raise RuntimeError("Container cannot be stopped.")

        container.state = ContainerState.STOPPED
        container.exit_code = exit_code
        container.stopped_at = datetime.now(timezone.utc).isoformat()

    def remove(self, container_id: str) -> None:
        container = self._get(container_id)

        if container.state in (
            ContainerState.RUNNING,
            ContainerState.PAUSED
        ):
            raise RuntimeError("Stop a container before removal.")

        container.state = ContainerState.REMOVED
        self.names.discard(container.name)
        del self.containers[container_id]

    def update_metrics(
        self,
        container_id: str,
        memory_mb: int,
        cpu_percent: float,
        process_count: int
    ) -> None:

        container = self._get(container_id)

        if container.state != ContainerState.RUNNING:
            raise RuntimeError("Metrics require a running container.")

        if memory_mb < 0 or cpu_percent < 0 or process_count < 0:
            raise ValidationError("Metrics cannot be negative.")

        if cpu_percent > 100 * container.limits.cpu_cores:
            raise ResourceLimitError("CPU usage exceeds configured capacity.")

        if memory_mb > container.limits.memory_mb:
            raise ResourceLimitError("Memory limit exceeded.")

        if process_count > container.limits.process_limit:
            raise ResourceLimitError("Process limit exceeded.")

        container.memory_used_mb = memory_mb
        container.cpu_used_percent = cpu_percent
        container.process_count = process_count

    def simulate_failure(self, container_id: str) -> None:
        container = self._get(container_id)

        if container.state != ContainerState.RUNNING:
            raise RuntimeError("Only running containers can fail.")

        container.state = ContainerState.FAILED
        container.exit_code = 137
        container.stopped_at = datetime.now(timezone.utc).isoformat()

        logger.error("Container failed: %s", container.name)

        if container.restart_policy == RestartPolicy.NEVER:
            return

        if container.restart_policy == RestartPolicy.ON_FAILURE:
            self._restart(container)

        elif container.restart_policy == RestartPolicy.ALWAYS:
            self._restart(container)

    def _restart(self, container: Container) -> None:
        # Production runtimes use backoff, restart limits and health policy.
        if container.restart_count >= 3:
            logger.error("Restart limit reached: %s", container.name)
            return

        container.restart_count += 1
        container.state = ContainerState.RUNNING
        container.started_at = datetime.now(timezone.utc).isoformat()
        container.stopped_at = None
        container.exit_code = None

        logger.info(
            "Container restarted: %s (%d)",
            container.name,
            container.restart_count
        )

    def list_containers(self) -> list[dict[str, Any]]:
        return [
            container.metrics()
            for container in self.containers.values()
        ]


class SecurityScanner:
    """Basic image policy checks, not a substitute for vulnerability scanning."""

    FORBIDDEN_PATTERNS = (
        "privileged=true",
        "password=",
        "root-login=true"
    )

    @classmethod
    def inspect(cls, image: ContainerImage) -> list[str]:
        findings = []

        for layer in image.layers:
            content = layer.content.lower()

            for pattern in cls.FORBIDDEN_PATTERNS:
                if pattern in content:
                    findings.append(
                        f"Potentially unsafe configuration in {layer.name}"
                    )

        if not image.digest:
            findings.append("Missing image digest.")

        return findings


def export_report(
    runtime: ContainerRuntime,
    path: str = "container_report.json"
) -> None:
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime_platform": platform.platform(),
        "containers": runtime.list_containers()
    }

    destination = Path(path)

    # Do not use untrusted input as a destination path in production.
    destination.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8"
    )


def run_demonstration() -> None:
    registry = ImageRegistry()

    image = ContainerImage(
        name="operations/api",
        version="1.0.0",
        layers=[
            ImageLayer("base", "minimal-linux-root-filesystem"),
            ImageLayer("runtime", "python-runtime-3.13"),
            ImageLayer("application", "operations-api-v1")
        ],
        entrypoint="python app.py",
        exposed_ports={8080}
    )

    registry.push(image)

    findings = SecurityScanner.inspect(image)

    if findings:
        raise ValidationError("; ".join(findings))

    runtime = ContainerRuntime(registry)

    api = runtime.create(
        image_reference="operations/api:1.0.0",
        name="operations-api",
        limits=ResourceLimits(
            cpu_cores=2,
            memory_mb=512,
            disk_mb=1024,
            process_limit=100
        ),
        environment={
            "APP_ENV": "production",
            "LOG_LEVEL": "INFO"
        },
        restart_policy=RestartPolicy.ON_FAILURE
    )

    runtime.start(api.container_id)

    runtime.update_metrics(
        api.container_id,
        memory_mb=180,
        cpu_percent=45,
        process_count=12
    )

    print("\nInitial container state:")
    print(json.dumps(api.metrics(), indent=2))

    runtime.simulate_failure(api.container_id)

    print("\nAfter failure and automatic restart:")
    print(json.dumps(api.metrics(), indent=2))

    runtime.pause(api.container_id)
    runtime.unpause(api.container_id)

    export_report(runtime)

    runtime.stop(api.container_id)
    runtime.remove(api.container_id)

    print("\nRemaining containers:")
    print(json.dumps(runtime.list_containers(), indent=2))


def run_tests() -> None:
    limits = ResourceLimits(memory_mb=128)

    assert limits.memory_mb == 128

    try:
        ResourceLimits(memory_mb=-1)
        raise AssertionError("Invalid resource limit was accepted.")
    except ValidationError:
        pass

    registry = ImageRegistry()

    image = ContainerImage(
        name="test/service",
        version="1.0",
        layers=[ImageLayer("base", "linux")],
        entrypoint="service"
    )

    registry.push(image)

    runtime = ContainerRuntime(registry)

    container = runtime.create(
        image.reference,
        "test-service",
        restart_policy=RestartPolicy.NEVER
    )

    runtime.start(container.container_id)

    try:
        runtime.start(container.container_id)
        raise AssertionError("Duplicate start was accepted.")
    except RuntimeError:
        pass

    try:
        runtime.update_metrics(
            container.container_id,
            memory_mb=9999,
            cpu_percent=10,
            process_count=1
        )
        raise AssertionError("Memory violation was accepted.")
    except ResourceLimitError:
        pass

    runtime.stop(container.container_id)
    runtime.remove(container.container_id)

    assert not runtime.list_containers()

    print("All container simulation tests passed.")


if __name__ == "__main__":
    run_tests()
    run_demonstration()
