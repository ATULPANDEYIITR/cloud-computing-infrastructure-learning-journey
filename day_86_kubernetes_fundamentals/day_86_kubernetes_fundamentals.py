#!/usr/bin/env python3
"""
Kubernetes Fundamentals: Cluster Orchestration Simulator

Demonstrates:
- Cluster, control plane, nodes, and workloads
- Declarative desired state and reconciliation
- Pods, Deployments, ReplicaSets, and Services
- Resource requests and scheduling
- Node capacity and health
- Readiness and liveness states
- Rolling updates and self-healing
- Scaling, validation, and failure handling

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import json
import logging
import random
import uuid

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)

logger = logging.getLogger("kubernetes")


class PodPhase(str, Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    FAILED = "Failed"
    TERMINATING = "Terminating"


class NodeStatus(str, Enum):
    READY = "Ready"
    NOT_READY = "NotReady"
    DRAINING = "Draining"


class DeploymentStatus(str, Enum):
    ACTIVE = "Active"
    DEGRADED = "Degraded"
    COMPLETE = "Complete"


class KubernetesError(Exception):
    """Base exception for cluster operations."""


class ValidationError(KubernetesError):
    pass


class SchedulingError(KubernetesError):
    pass


@dataclass(frozen=True)
class ResourceRequirements:
    cpu_millicores: int
    memory_mb: int

    def __post_init__(self):
        if self.cpu_millicores <= 0 or self.memory_mb <= 0:
            raise ValidationError("Resource requests must be positive.")


@dataclass
class Pod:
    name: str
    image: str
    resources: ResourceRequirements
    labels: dict[str, str]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    phase: PodPhase = PodPhase.PENDING
    node_name: Optional[str] = None
    ready: bool = False
    restart_count: int = 0
    creation_generation: int = 1

    def __post_init__(self):
        if not self.name or not self.image:
            raise ValidationError("Pod name and image are required.")

        if not isinstance(self.labels, dict):
            raise ValidationError("Labels must be a dictionary.")


@dataclass
class Node:
    name: str
    cpu_capacity: int
    memory_capacity: int
    status: NodeStatus = NodeStatus.READY
    pods: dict[str, Pod] = field(default_factory=dict)

    def __post_init__(self):
        if self.cpu_capacity <= 0 or self.memory_capacity <= 0:
            raise ValidationError("Node capacity must be positive.")

    @property
    def allocated_cpu(self) -> int:
        return sum(
            pod.resources.cpu_millicores
            for pod in self.pods.values()
            if pod.phase in (PodPhase.RUNNING, PodPhase.PENDING)
        )

    @property
    def allocated_memory(self) -> int:
        return sum(
            pod.resources.memory_mb
            for pod in self.pods.values()
            if pod.phase in (PodPhase.RUNNING, PodPhase.PENDING)
        )

    def can_schedule(self, pod: Pod) -> bool:
        return (
            self.status == NodeStatus.READY
            and self.allocated_cpu + pod.resources.cpu_millicores
            <= self.cpu_capacity
            and self.allocated_memory + pod.resources.memory_mb
            <= self.memory_capacity
        )

    def utilization(self) -> float:
        if self.cpu_capacity == 0:
            return 100.0

        return self.allocated_cpu / self.cpu_capacity


@dataclass
class Deployment:
    name: str
    image: str
    replicas: int
    selector: dict[str, str]
    resources: ResourceRequirements
    generation: int = 1
    pods: dict[str, Pod] = field(default_factory=dict)

    def __post_init__(self):
        if not self.name or not self.image:
            raise ValidationError("Deployment name and image are required.")

        if self.replicas < 0:
            raise ValidationError("Replica count cannot be negative.")

        if not self.selector:
            raise ValidationError("Deployment selector cannot be empty.")


@dataclass
class Service:
    name: str
    selector: dict[str, str]
    port: int
    target_port: int

    def __post_init__(self):
        if not (1 <= self.port <= 65535):
            raise ValidationError("Invalid service port.")

        if not (1 <= self.target_port <= 65535):
            raise ValidationError("Invalid target port.")

    def matches(self, pod: Pod) -> bool:
        return all(
            pod.labels.get(key) == value
            for key, value in self.selector.items()
        )


class Scheduler:
    """
    Resource-aware scheduler.

    Selects the feasible node with the lowest CPU utilization.
    Scheduling cost is O(N) per pod for N cluster nodes.
    """

    def schedule(self, pod: Pod, nodes: list[Node]) -> Node:
        candidates = [
            node for node in nodes
            if node.can_schedule(pod)
        ]

        if not candidates:
            raise SchedulingError(
                f"No feasible node for pod {pod.name}"
            )

        candidates.sort(
            key=lambda node: (
                node.utilization(),
                node.allocated_memory / node.memory_capacity,
                node.name
            )
        )

        selected = candidates[0]

        selected.pods[pod.id] = pod
        pod.node_name = selected.name
        pod.phase = PodPhase.RUNNING

        logger.info(
            "Scheduled %s on %s",
            pod.name,
            selected.name
        )

        return selected


class KubernetesCluster:
    """
    Simplified control-plane and worker-node simulation.

    Desired state is stored in Deployments.
    Actual state is represented by scheduled Pods.
    The reconciliation loop attempts to make actual state
    converge toward desired state.
    """

    def __init__(self, name: str):
        if not name:
            raise ValidationError("Cluster name is required.")

        self.name = name
        self.nodes: dict[str, Node] = {}
        self.deployments: dict[str, Deployment] = {}
        self.services: dict[str, Service] = {}
        self.scheduler = Scheduler()
        self.events: list[dict] = []
        self.reconciliation_count = 0

    def record_event(self, event_type: str, message: str):
        self.events.append({
            "type": event_type,
            "message": message,
            "sequence": len(self.events) + 1
        })

    def add_node(self, node: Node):
        if node.name in self.nodes:
            raise ValidationError("Duplicate node name.")

        self.nodes[node.name] = node
        self.record_event("NodeAdded", node.name)

    def deploy(self, deployment: Deployment):
        if deployment.name in self.deployments:
            raise ValidationError("Deployment already exists.")

        self.deployments[deployment.name] = deployment
        self.record_event(
            "DeploymentCreated",
            deployment.name
        )

    def create_service(self, service: Service):
        if service.name in self.services:
            raise ValidationError("Service already exists.")

        self.services[service.name] = service
        self.record_event("ServiceCreated", service.name)

    def reconcile(self):
        """
        Reconciliation creates missing replicas and removes
        excess replicas.

        Failed pods are replaced rather than counted as
        healthy running replicas.
        """
        self.reconciliation_count += 1

        for deployment in self.deployments.values():

            active = [
                pod for pod in deployment.pods.values()
                if pod.phase in (
                    PodPhase.PENDING,
                    PodPhase.RUNNING
                )
            ]

            while len(active) < deployment.replicas:
                index = len(deployment.pods) + 1

                pod = Pod(
                    name=f"{deployment.name}-{index}",
                    image=deployment.image,
                    resources=deployment.resources,
                    labels=dict(deployment.selector),
                    creation_generation=deployment.generation
                )

                deployment.pods[pod.id] = pod

                try:
                    self.scheduler.schedule(
                        pod,
                        list(self.nodes.values())
                    )
                    pod.ready = True
                    self.record_event(
                        "PodScheduled",
                        pod.name
                    )

                except SchedulingError as exc:
                    logger.warning("%s", exc)
                    deployment.pods.pop(pod.id)
                    break

                active.append(pod)

            if len(active) > deployment.replicas:
                excess = len(active) - deployment.replicas

                for pod in active[:excess]:
                    self.delete_pod(pod)

    def delete_pod(self, pod: Pod):
        pod.phase = PodPhase.TERMINATING
        pod.ready = False

        if pod.node_name in self.nodes:
            self.nodes[pod.node_name].pods.pop(pod.id, None)

        pod.phase = PodPhase.FAILED
        pod.node_name = None

        self.record_event("PodDeleted", pod.name)

    def fail_pod(self, deployment_name: str, pod_id: str):
        deployment = self.deployments[deployment_name]
        pod = deployment.pods[pod_id]

        if pod.node_name in self.nodes:
            self.nodes[pod.node_name].pods.pop(pod.id, None)

        pod.phase = PodPhase.FAILED
        pod.ready = False
        pod.restart_count += 1
        pod.node_name = None

        self.record_event("PodFailed", pod.name)

    def scale(self, deployment_name: str, replicas: int):
        if replicas < 0:
            raise ValidationError("Replicas cannot be negative.")

        deployment = self.deployments[deployment_name]
        deployment.replicas = replicas
        deployment.generation += 1

        self.record_event(
            "DeploymentScaled",
            f"{deployment_name}: {replicas}"
        )

        self.reconcile()

    def rolling_update(self, deployment_name: str, new_image: str):
        if not new_image:
            raise ValidationError("Image cannot be empty.")

        deployment = self.deployments[deployment_name]

        old_image = deployment.image
        old_generation = deployment.generation

        deployment.image = new_image
        deployment.generation += 1

        # Replace one replica at a time, preserving availability
        # where sufficient cluster capacity exists.
        try:
            for pod in list(deployment.pods.values()):
                if pod.phase != PodPhase.RUNNING:
                    continue

                replacement = Pod(
                    name=f"{deployment.name}-g{deployment.generation}-"
                         f"{len(deployment.pods) + 1}",
                    image=new_image,
                    resources=deployment.resources,
                    labels=dict(deployment.selector),
                    creation_generation=deployment.generation
                )

                self.scheduler.schedule(
                    replacement,
                    list(self.nodes.values())
                )

                replacement.ready = True
                deployment.pods[replacement.id] = replacement

                self.delete_pod(pod)
                deployment.pods.pop(pod.id, None)

        except SchedulingError:
            deployment.image = old_image
            deployment.generation = old_generation

            # Keep already completed replacements visible.
            logger.error(
                "Rolling update interrupted by insufficient capacity."
            )

            self.record_event(
                "RollingUpdateInterrupted",
                deployment_name
            )
            return False

        self.record_event(
            "RollingUpdateCompleted",
            deployment_name
        )

        return True

    def mark_node_unready(self, node_name: str):
        node = self.nodes[node_name]
        node.status = NodeStatus.NOT_READY

        for pod in list(node.pods.values()):
            deployment = next(
                (
                    deployment
                    for deployment in self.deployments.values()
                    if pod.id in deployment.pods
                ),
                None
            )

            pod.phase = PodPhase.FAILED
            pod.ready = False
            pod.node_name = None
            pod.restart_count += 1

            node.pods.pop(pod.id, None)

            if deployment:
                self.record_event(
                    "PodEvicted",
                    pod.name
                )

        self.record_event("NodeNotReady", node_name)

    def service_endpoints(self, service_name: str) -> list[str]:
        service = self.services[service_name]

        return [
            pod.name
            for deployment in self.deployments.values()
            for pod in deployment.pods.values()
            if (
                pod.phase == PodPhase.RUNNING
                and pod.ready
                and service.matches(pod)
            )
        ]

    def deployment_status(self, name: str) -> DeploymentStatus:
        deployment = self.deployments[name]

        ready = sum(
            1 for pod in deployment.pods.values()
            if pod.phase == PodPhase.RUNNING and pod.ready
        )

        if ready == deployment.replicas:
            return DeploymentStatus.COMPLETE

        if ready == 0 and deployment.replicas > 0:
            return DeploymentStatus.DEGRADED

        return DeploymentStatus.ACTIVE

    def snapshot(self) -> dict:
        return {
            "cluster": self.name,
            "reconciliation_count": self.reconciliation_count,
            "nodes": [
                {
                    "name": node.name,
                    "status": node.status.value,
                    "cpu_capacity": node.cpu_capacity,
                    "cpu_allocated": node.allocated_cpu,
                    "memory_capacity_mb": node.memory_capacity,
                    "memory_allocated_mb": node.allocated_memory,
                    "pod_count": len(node.pods)
                }
                for node in self.nodes.values()
            ],
            "deployments": [
                {
                    "name": deployment.name,
                    "image": deployment.image,
                    "desired_replicas": deployment.replicas,
                    "actual_replicas": sum(
                        pod.phase == PodPhase.RUNNING
                        for pod in deployment.pods.values()
                    ),
                    "status": self.deployment_status(
                        deployment.name
                    ).value
                }
                for deployment in self.deployments.values()
            ],
            "services": {
                name: self.service_endpoints(name)
                for name in self.services
            },
            "events": self.events
        }


def demonstrate_cluster():
    cluster = KubernetesCluster("production-cluster")

    cluster.add_node(
        Node("worker-01", 4000, 8192)
    )

    cluster.add_node(
        Node("worker-02", 4000, 8192)
    )

    cluster.add_node(
        Node("worker-03", 2000, 4096)
    )

    deployment = Deployment(
        name="payment-api",
        image="registry.example.com/payment-api:v1",
        replicas=3,
        selector={"app": "payment-api"},
        resources=ResourceRequirements(
            cpu_millicores=500,
            memory_mb=512
        )
    )

    cluster.deploy(deployment)

    cluster.create_service(
        Service(
            name="payment-service",
            selector={"app": "payment-api"},
            port=80,
            target_port=8080
        )
    )

    print("\nINITIAL RECONCILIATION")
    cluster.reconcile()

    print(json.dumps(cluster.snapshot(), indent=2))

    print("\nSIMULATING POD FAILURE")

    pod = next(iter(deployment.pods.values()))
    cluster.fail_pod(deployment.name, pod.id)

    cluster.reconcile()

    print("\nSCALING TO FOUR REPLICAS")
    cluster.scale("payment-api", 4)

    print("\nROLLING UPDATE")
    success = cluster.rolling_update(
        "payment-api",
        "registry.example.com/payment-api:v2"
    )

    print("Rolling update:", success)

    print("\nNODE FAILURE")
    cluster.mark_node_unready("worker-03")
    cluster.reconcile()

    print("\nFINAL CLUSTER STATE")
    print(json.dumps(cluster.snapshot(), indent=2))

    print("\nSERVICE ENDPOINTS")
    print(cluster.service_endpoints("payment-service"))

    # Validate fundamental orchestration behavior.
    assert cluster.reconciliation_count >= 4
    assert len(cluster.service_endpoints("payment-service")) >= 0

    print("\nSimulation completed successfully.")


if __name__ == "__main__":
    random.seed(42)
    demonstrate_cluster()
