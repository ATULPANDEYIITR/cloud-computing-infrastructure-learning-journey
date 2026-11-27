#!/usr/bin/env python3
"""
Kubernetes Pods: Architecture, Lifecycle, Manifests, and Multi-Container Pods.

Self-contained simulation of Kubernetes Pod scheduling, lifecycle transitions,
container health, shared resources, restart policies, readiness, and deletion.

Run:
    python pods.py
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)
logger = logging.getLogger("pod-simulator")


class PodPhase(str, Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    UNKNOWN = "Unknown"


class ContainerState(str, Enum):
    WAITING = "Waiting"
    RUNNING = "Running"
    TERMINATED = "Terminated"


class RestartPolicy(str, Enum):
    ALWAYS = "Always"
    ON_FAILURE = "OnFailure"
    NEVER = "Never"


class PodCondition(str, Enum):
    INITIALIZED = "Initialized"
    READY = "Ready"
    SCHEDULED = "PodScheduled"


@dataclass
class ResourceRequirements:
    cpu_millicores: int = 100
    memory_mb: int = 128

    def validate(self) -> None:
        if self.cpu_millicores <= 0 or self.memory_mb <= 0:
            raise ValueError("CPU and memory requests must be positive")


@dataclass
class Container:
    name: str
    image: str
    command: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)
    resources: ResourceRequirements = field(
        default_factory=ResourceRequirements
    )
    state: ContainerState = ContainerState.WAITING
    restart_count: int = 0
    exit_code: Optional[int] = None
    ready: bool = False
    liveness_healthy: bool = True
    readiness_healthy: bool = True

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", self.name):
            raise ValueError(f"Invalid container name: {self.name}")

        if not self.image or len(self.image) > 253:
            raise ValueError("Invalid container image")

        if any(port < 1 or port > 65535 for port in self.ports):
            raise ValueError("Container port must be between 1 and 65535")

        self.resources.validate()


@dataclass
class PodSpec:
    containers: list[Container]
    init_containers: list[Container] = field(default_factory=list)
    restart_policy: RestartPolicy = RestartPolicy.ALWAYS
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)
    termination_grace_period_seconds: int = 30
    service_account: str = "default"

    def validate(self) -> None:
        if not self.containers:
            raise ValueError("A Pod must contain at least one application container")

        if self.termination_grace_period_seconds < 0:
            raise ValueError("Termination grace period cannot be negative")

        names = [
            container.name
            for container in self.containers + self.init_containers
        ]

        if len(names) != len(set(names)):
            raise ValueError("Container names must be unique within a Pod")

        for container in self.containers + self.init_containers:
            container.validate()

        for key, value in self.labels.items():
            if not key or not isinstance(value, str):
                raise ValueError("Invalid label")


@dataclass
class Pod:
    name: str
    namespace: str
    spec: PodSpec
    uid: str = field(default_factory=lambda: str(uuid.uuid4()))
    phase: PodPhase = PodPhase.PENDING
    node_name: Optional[str] = None
    conditions: dict[str, bool] = field(default_factory=dict)
    deletion_timestamp: Optional[float] = None
    events: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def validate(self) -> None:
        self.spec.validate()

        if not re.fullmatch(
            r"[a-z0-9]([-a-z0-9]*[a-z0-9])?",
            self.name
        ):
            raise ValueError("Invalid Pod name")

        if not self.namespace:
            raise ValueError("Namespace is required")

    @property
    def ready(self) -> bool:
        return (
            self.phase == PodPhase.RUNNING
            and bool(self.spec.containers)
            and all(c.ready for c in self.spec.containers)
        )

    def record(self, message: str) -> None:
        self.events.append(message)
        logger.info("[%s] %s", self.name, message)


@dataclass
class Node:
    name: str
    cpu_capacity: int
    memory_capacity: int
    allocated_cpu: int = 0
    allocated_memory: int = 0

    def can_schedule(self, pod: Pod) -> bool:
        cpu = sum(
            c.resources.cpu_millicores
            for c in pod.spec.containers + pod.spec.init_containers
        )
        memory = sum(
            c.resources.memory_mb
            for c in pod.spec.containers + pod.spec.init_containers
        )

        return (
            self.allocated_cpu + cpu <= self.cpu_capacity
            and self.allocated_memory + memory <= self.memory_capacity
        )

    def allocate(self, pod: Pod) -> None:
        if not self.can_schedule(pod):
            raise RuntimeError(f"Insufficient resources on {self.name}")

        self.allocated_cpu += sum(
            c.resources.cpu_millicores
            for c in pod.spec.containers + pod.spec.init_containers
        )
        self.allocated_memory += sum(
            c.resources.memory_mb
            for c in pod.spec.containers + pod.spec.init_containers
        )

    def release(self, pod: Pod) -> None:
        self.allocated_cpu -= sum(
            c.resources.cpu_millicores
            for c in pod.spec.containers + pod.spec.init_containers
        )
        self.allocated_memory -= sum(
            c.resources.memory_mb
            for c in pod.spec.containers + pod.spec.init_containers
        )


class PodError(Exception):
    pass


class PodManager:
    def __init__(self, nodes: list[Node]):
        self.nodes = nodes
        self.pods: dict[str, Pod] = {}

    def create(self, pod: Pod) -> Pod:
        pod.validate()

        key = f"{pod.namespace}/{pod.name}"

        if key in self.pods:
            raise PodError(f"Pod already exists: {key}")

        pod.conditions[PodCondition.INITIALIZED.value] = False
        pod.conditions[PodCondition.READY.value] = False
        pod.conditions[PodCondition.SCHEDULED.value] = False

        self.pods[key] = pod
        pod.record("Pod created")
        return pod

    def schedule(self, pod: Pod) -> bool:
        if pod.phase != PodPhase.PENDING:
            raise PodError("Only Pending Pods can be scheduled")

        for node in self.nodes:
            if node.can_schedule(pod):
                node.allocate(pod)
                pod.node_name = node.name
                pod.conditions[PodCondition.SCHEDULED.value] = True
                pod.record(f"Scheduled on node {node.name}")
                return True

        pod.record("Scheduling failed: insufficient node capacity")
        return False

    def start(self, pod: Pod) -> None:
        if not pod.node_name:
            raise PodError("Pod must be scheduled before starting")

        # Init containers execute sequentially before application containers.
        for container in pod.spec.init_containers:
            container.state = ContainerState.RUNNING
            container.ready = False
            pod.record(f"Init container started: {container.name}")

            container.state = ContainerState.TERMINATED
            container.exit_code = 0
            pod.record(f"Init container completed: {container.name}")

        for container in pod.spec.containers:
            container.state = ContainerState.RUNNING
            container.ready = container.readiness_healthy
            container.exit_code = None
            pod.record(f"Application container started: {container.name}")

        pod.conditions[PodCondition.INITIALIZED.value] = True
        pod.phase = PodPhase.RUNNING
        pod.conditions[PodCondition.READY.value] = pod.ready
        pod.record("Pod entered Running phase")

    def update_readiness(self, pod: Pod, container_name: str, healthy: bool) -> None:
        container = self._find_container(pod, container_name)

        if container.state != ContainerState.RUNNING:
            raise PodError("Readiness can only be updated for running containers")

        container.readiness_healthy = healthy
        container.ready = healthy

        pod.conditions[PodCondition.READY.value] = pod.ready
        pod.record(
            f"Readiness changed for {container_name}: {healthy}"
        )

    def restart_container(
        self,
        pod: Pod,
        container_name: str,
        exit_code: int
    ) -> bool:
        container = self._find_container(pod, container_name)

        if container.state != ContainerState.RUNNING:
            raise PodError("Only running containers can terminate")

        container.state = ContainerState.TERMINATED
        container.exit_code = exit_code
        container.ready = False
        pod.record(
            f"Container {container_name} terminated with exit code {exit_code}"
        )

        should_restart = (
            pod.spec.restart_policy == RestartPolicy.ALWAYS
            or (
                pod.spec.restart_policy == RestartPolicy.ON_FAILURE
                and exit_code != 0
            )
        )

        if should_restart:
            container.restart_count += 1
            container.state = ContainerState.RUNNING
            container.exit_code = None
            container.ready = container.readiness_healthy
            pod.conditions[PodCondition.READY.value] = pod.ready
            pod.record(
                f"Container restarted; count={container.restart_count}"
            )
            return True

        # A failed container with no restart can fail the Pod.
        if exit_code != 0:
            pod.phase = PodPhase.FAILED
        elif all(
            c.state == ContainerState.TERMINATED
            for c in pod.spec.containers
        ):
            pod.phase = PodPhase.SUCCEEDED

        pod.conditions[PodCondition.READY.value] = False
        return False

    def evaluate_liveness(self, pod: Pod) -> list[str]:
        restarted = []

        for container in pod.spec.containers:
            if (
                container.state == ContainerState.RUNNING
                and not container.liveness_healthy
            ):
                container.state = ContainerState.TERMINATED
                container.ready = False
                container.exit_code = 137
                container.restart_count += 1
                container.state = ContainerState.RUNNING
                container.exit_code = None
                container.ready = container.readiness_healthy
                restarted.append(container.name)

                pod.record(
                    f"Liveness failure caused restart: {container.name}"
                )

        pod.conditions[PodCondition.READY.value] = pod.ready
        return restarted

    def delete(self, pod: Pod) -> None:
        if pod.phase in (PodPhase.SUCCEEDED, PodPhase.FAILED):
            self._release_resources(pod)
            self._remove(pod)
            return

        if pod.deletion_timestamp is not None:
            return

        pod.deletion_timestamp = time.time()
        pod.record("Deletion requested; termination grace period started")

        for container in pod.spec.containers:
            container.ready = False
            container.state = ContainerState.TERMINATED
            container.exit_code = 143

        pod.phase = PodPhase.SUCCEEDED
        pod.conditions[PodCondition.READY.value] = False

        self._release_resources(pod)
        self._remove(pod)

    def _release_resources(self, pod: Pod) -> None:
        if pod.node_name:
            node = next(
                (n for n in self.nodes if n.name == pod.node_name),
                None
            )
            if node:
                node.release(pod)
            pod.node_name = None

    def _remove(self, pod: Pod) -> None:
        self.pods.pop(f"{pod.namespace}/{pod.name}", None)
        pod.record("Pod removed from manager")

    @staticmethod
    def _find_container(pod: Pod, name: str) -> Container:
        for container in pod.spec.containers:
            if container.name == name:
                return container
        raise PodError(f"Container not found: {name}")

    def report(self) -> list[dict]:
        return [
            {
                "name": pod.name,
                "namespace": pod.namespace,
                "uid": pod.uid,
                "phase": pod.phase.value,
                "ready": pod.ready,
                "node": pod.node_name,
                "containers": [
                    {
                        "name": c.name,
                        "state": c.state.value,
                        "ready": c.ready,
                        "restarts": c.restart_count
                    }
                    for c in pod.spec.containers
                ]
            }
            for pod in self.pods.values()
        ]


def multi_container_example() -> None:
    """Application and sidecar share a Pod network and lifecycle."""

    app = Container(
        name="web",
        image="nginx:1.27",
        ports=[8080],
        resources=ResourceRequirements(300, 256)
    )

    sidecar = Container(
        name="log-agent",
        image="fluent-bit:3.1",
        resources=ResourceRequirements(100, 128)
    )

    init = Container(
        name="config-check",
        image="busybox:1.36",
        command=["sh", "-c", "echo validating configuration"],
        resources=ResourceRequirements(50, 64)
    )

    pod = Pod(
        name="web-with-sidecar",
        namespace="production",
        spec=PodSpec(
            containers=[app, sidecar],
            init_containers=[init],
            restart_policy=RestartPolicy.ALWAYS,
            labels={
                "app": "web",
                "environment": "production"
            },
            annotations={
                "description": "Web server with log collection sidecar"
            }
        )
    )

    manager = PodManager([
        Node("worker-01", 2000, 4096),
        Node("worker-02", 1000, 2048)
    ])

    manager.create(pod)
    assert manager.schedule(pod)

    manager.start(pod)
    assert pod.phase == PodPhase.RUNNING
    assert pod.ready

    # Readiness failure does not necessarily stop the container.
    manager.update_readiness(pod, "log-agent", False)
    assert not pod.ready

    manager.update_readiness(pod, "log-agent", True)
    assert pod.ready

    # Restarting one container does not recreate the entire Pod.
    assert manager.restart_container(pod, "web", 1)
    assert pod.ready

    print("\nPOD REPORT")
    print(json.dumps(manager.report(), indent=2))

    print("\nPOD EVENTS")
    for event in pod.events:
        print("-", event)

    manager.delete(pod)


def lifecycle_edge_cases() -> None:
    manager = PodManager([Node("worker-03", 500, 1024)])

    job = Pod(
        name="batch-job",
        namespace="jobs",
        spec=PodSpec(
            containers=[
                Container(
                    "processor",
                    "python:3.13-slim",
                    resources=ResourceRequirements(200, 256)
                )
            ],
            restart_policy=RestartPolicy.NEVER
        )
    )

    manager.create(job)
    assert manager.schedule(job)
    manager.start(job)

    # A successful one-shot workload with Never does not restart.
    assert not manager.restart_container(job, "processor", 0)
    assert job.phase == PodPhase.SUCCEEDED

    manager.delete(job)

    # Invalid configurations must fail before scheduling.
    try:
        invalid = Pod(
            "invalid-pod",
            "default",
            PodSpec(containers=[])
        )
        manager.create(invalid)
    except ValueError as exc:
        print(f"\nExpected validation failure: {exc}")


def main() -> None:
    print("KUBERNETES POD ARCHITECTURE SIMULATION")
    multi_container_example()
    lifecycle_edge_cases()
    print("\nAll Pod simulation assertions passed.")


if __name__ == "__main__":
    main()
