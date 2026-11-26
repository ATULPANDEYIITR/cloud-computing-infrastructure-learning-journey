#!/usr/bin/env python3
"""
Kubernetes Control Plane Simulation

Models:
- API server and request validation
- etcd-style persistent cluster state
- Scheduler and node selection
- Controllers and reconciliation loops
- Deployment and ReplicaSet management
- Resource versions and optimistic concurrency
- Cluster health and failure handling

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import copy
import json
import logging
import time
import uuid

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s"
)

logger = logging.getLogger("kubernetes-control-plane")


# ============================================================
# DOMAIN ENUMS
# ============================================================

class PodPhase(str, Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    FAILED = "Failed"
    SUCCEEDED = "Succeeded"


class NodeCondition(str, Enum):
    READY = "Ready"
    NOT_READY = "NotReady"


class ObjectKind(str, Enum):
    POD = "Pod"
    DEPLOYMENT = "Deployment"
    NODE = "Node"


# ============================================================
# EXCEPTIONS
# ============================================================

class ControlPlaneError(Exception):
    pass


class ValidationError(ControlPlaneError):
    pass


class NotFoundError(ControlPlaneError):
    pass


class ConflictError(ControlPlaneError):
    pass


class SchedulingError(ControlPlaneError):
    pass


# ============================================================
# DOMAIN MODELS
# ============================================================

@dataclass
class Resource:
    name: str
    namespace: str = "default"
    uid: str = field(default_factory=lambda: str(uuid.uuid4()))
    resource_version: int = 0
    labels: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.name or len(self.name) > 253:
            raise ValidationError("Invalid resource name")

        if not self.namespace:
            raise ValidationError("Namespace is required")


@dataclass
class Node(Resource):
    capacity_cpu: int = 4
    capacity_memory: int = 8192
    allocatable_cpu: int = 4
    allocatable_memory: int = 8192
    condition: NodeCondition = NodeCondition.READY
    used_cpu: int = 0
    used_memory: int = 0

    def available_cpu(self) -> int:
        return self.allocatable_cpu - self.used_cpu

    def available_memory(self) -> int:
        return self.allocatable_memory - self.used_memory


@dataclass
class Pod(Resource):
    image: str = "nginx:stable"
    cpu_request: int = 1
    memory_request: int = 256
    phase: PodPhase = PodPhase.PENDING
    node_name: Optional[str] = None
    owner: Optional[str] = None

    def validate(self) -> None:
        super().validate()

        if not self.image:
            raise ValidationError("Container image is required")

        if self.cpu_request <= 0:
            raise ValidationError("CPU request must be positive")

        if self.memory_request <= 0:
            raise ValidationError("Memory request must be positive")


@dataclass
class Deployment(Resource):
    replicas: int = 1
    selector: dict[str, str] = field(default_factory=dict)
    template_image: str = "nginx:stable"
    cpu_request: int = 1
    memory_request: int = 256

    def validate(self) -> None:
        super().validate()

        if self.replicas < 0 or self.replicas > 10000:
            raise ValidationError("Invalid replica count")

        if not self.selector:
            raise ValidationError("Deployment selector is required")

        if not self.template_image:
            raise ValidationError("Container image is required")


# ============================================================
# ETCD-STYLE PERSISTENT STATE
# ============================================================

class EtcdStore:
    """
    Simplified versioned key-value store.

    Every successful write receives a monotonically increasing
    revision. Compare-and-swap prevents lost updates.
    """

    def __init__(self):
        self._data: dict[str, Any] = {}
        self._revision = 0
        self._history: list[dict[str, Any]] = []

    @property
    def revision(self) -> int:
        return self._revision

    def get(self, key: str) -> tuple[Any, int]:
        if key not in self._data:
            raise NotFoundError(f"Key not found: {key}")

        value = copy.deepcopy(self._data[key])
        return value, value.resource_version

    def list(self, prefix: str) -> list[Any]:
        return [
            copy.deepcopy(value)
            for key, value in self._data.items()
            if key.startswith(prefix)
        ]

    def put(
        self,
        key: str,
        value: Resource,
        expected_version: Optional[int] = None
    ) -> Resource:

        current = self._data.get(key)

        if expected_version is not None:
            actual = current.resource_version if current else 0

            if actual != expected_version:
                raise ConflictError(
                    f"Version conflict: expected {expected_version}, "
                    f"found {actual}"
                )

        self._revision += 1

        stored = copy.deepcopy(value)
        stored.resource_version = self._revision

        self._data[key] = stored

        self._history.append({
            "revision": self._revision,
            "key": key,
            "operation": "PUT"
        })

        return copy.deepcopy(stored)

    def delete(
        self,
        key: str,
        expected_version: Optional[int] = None
    ) -> None:

        if key not in self._data:
            raise NotFoundError(key)

        current = self._data[key]

        if expected_version is not None:
            if current.resource_version != expected_version:
                raise ConflictError("Delete version conflict")

        del self._data[key]
        self._revision += 1

        self._history.append({
            "revision": self._revision,
            "key": key,
            "operation": "DELETE"
        })

    def history(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._history)


# ============================================================
# API SERVER
# ============================================================

class APIServer:
    """
    Central cluster API.

    Clients submit desired state through this interface.
    The API server validates and persists objects.
    """

    def __init__(self, store: EtcdStore):
        self.store = store
        self.audit_log: list[dict[str, Any]] = []

    @staticmethod
    def key(kind: ObjectKind, resource: Resource) -> str:
        return (
            f"/registry/{kind.value.lower()}/"
            f"{resource.namespace}/{resource.name}"
        )

    def create(
        self,
        kind: ObjectKind,
        resource: Resource
    ) -> Resource:

        resource.validate()
        key = self.key(kind, resource)

        if self.store.list(key):
            raise ConflictError(f"Resource already exists: {key}")

        saved = self.store.put(key, resource, expected_version=0)

        self._audit("CREATE", key, saved.resource_version)
        return saved

    def update(
        self,
        kind: ObjectKind,
        resource: Resource,
        expected_version: int
    ) -> Resource:

        resource.validate()
        key = self.key(kind, resource)

        saved = self.store.put(
            key,
            resource,
            expected_version=expected_version
        )

        self._audit("UPDATE", key, saved.resource_version)
        return saved

    def get(
        self,
        kind: ObjectKind,
        namespace: str,
        name: str
    ) -> Resource:

        key = f"/registry/{kind.value.lower()}/{namespace}/{name}"
        resource, _ = self.store.get(key)
        return resource

    def list(self, kind: ObjectKind) -> list[Resource]:
        return self.store.list(
            f"/registry/{kind.value.lower()}/"
        )

    def _audit(
        self,
        operation: str,
        key: str,
        revision: int
    ) -> None:

        self.audit_log.append({
            "operation": operation,
            "key": key,
            "revision": revision,
            "timestamp": time.time()
        })


# ============================================================
# SCHEDULER
# ============================================================

class Scheduler:
    """
    Assigns unscheduled Pods to suitable Nodes.

    Scheduling considers readiness and requested resources.
    """

    def __init__(self, api: APIServer):
        self.api = api
        self.scheduling_events: list[dict[str, str]] = []

    def schedule(self, pod: Pod) -> Optional[str]:

        candidates = [
            node
            for node in self.api.list(ObjectKind.NODE)
            if isinstance(node, Node)
            and node.condition == NodeCondition.READY
            and node.available_cpu() >= pod.cpu_request
            and node.available_memory() >= pod.memory_request
        ]

        if not candidates:
            self.scheduling_events.append({
                "pod": pod.name,
                "result": "Unschedulable"
            })
            return None

        # Prefer the node with the most remaining CPU capacity.
        candidates.sort(
            key=lambda n: (
                n.available_cpu() - pod.cpu_request,
                n.available_memory() - pod.memory_request
            ),
            reverse=True
        )

        node = candidates[0]

        node.used_cpu += pod.cpu_request
        node.used_memory += pod.memory_request

        updated_node = self.api.update(
            ObjectKind.NODE,
            node,
            node.resource_version
        )

        pod.node_name = updated_node.name
        pod.phase = PodPhase.RUNNING

        self.api.update(
            ObjectKind.POD,
            pod,
            pod.resource_version
        )

        self.scheduling_events.append({
            "pod": pod.name,
            "result": f"Scheduled on {node.name}"
        })

        return node.name


# ============================================================
# CONTROLLER MANAGER
# ============================================================

class DeploymentController:
    """
    Reconciliation loop.

    Desired replicas are compared with actual owned Pods.
    Missing Pods are created and excess Pods are removed.
    """

    def __init__(self, api: APIServer):
        self.api = api
        self.reconciliation_count = 0

    @staticmethod
    def matches(
        pod: Pod,
        selector: dict[str, str]
    ) -> bool:
        return all(
            pod.labels.get(key) == value
            for key, value in selector.items()
        )

    def reconcile(
        self,
        deployment: Deployment
    ) -> dict[str, int]:

        self.reconciliation_count += 1

        pods = [
            pod
            for pod in self.api.list(ObjectKind.POD)
            if isinstance(pod, Pod)
            and pod.namespace == deployment.namespace
            and pod.owner == deployment.uid
            and self.matches(pod, deployment.selector)
        ]

        running = [
            pod for pod in pods
            if pod.phase == PodPhase.RUNNING
        ]

        missing = max(0, deployment.replicas - len(running))
        excess = max(0, len(pods) - deployment.replicas)

        for pod in sorted(
            pods,
            key=lambda item: item.name,
            reverse=True
        )[:excess]:

            if pod.node_name:
                self._release_resources(pod)

            self.api.store.delete(
                self.api.key(ObjectKind.POD, pod),
                pod.resource_version
            )

        created = 0

        for index in range(missing):
            pod = Pod(
                name=(
                    f"{deployment.name}-"
                    f"{self.reconciliation_count}-{index}"
                ),
                namespace=deployment.namespace,
                image=deployment.template_image,
                cpu_request=deployment.cpu_request,
                memory_request=deployment.memory_request,
                labels=deployment.selector.copy(),
                owner=deployment.uid
            )

            self.api.create(ObjectKind.POD, pod)
            created += 1

        return {
            "desired": deployment.replicas,
            "actual_running": len(running),
            "created": created,
            "removed": excess
        }

    def _release_resources(self, pod: Pod) -> None:

        node = self.api.get(
            ObjectKind.NODE,
            "default",
            pod.node_name
        )

        if not isinstance(node, Node):
            return

        node.used_cpu = max(0, node.used_cpu - pod.cpu_request)
        node.used_memory = max(
            0,
            node.used_memory - pod.memory_request
        )

        self.api.update(
            ObjectKind.NODE,
            node,
            node.resource_version
        )


class ControlPlane:
    """
    Coordinates API operations, scheduling and reconciliation.
    """

    def __init__(self):
        self.etcd = EtcdStore()
        self.api = APIServer(self.etcd)
        self.scheduler = Scheduler(self.api)
        self.controller = DeploymentController(self.api)

    def add_node(
        self,
        name: str,
        cpu: int,
        memory: int
    ) -> Node:

        if cpu <= 0 or memory <= 0:
            raise ValidationError("Node capacity must be positive")

        node = Node(
            name=name,
            capacity_cpu=cpu,
            capacity_memory=memory,
            allocatable_cpu=cpu,
            allocatable_memory=memory
        )

        return self.api.create(ObjectKind.NODE, node)

    def deploy(self, deployment: Deployment) -> None:

        self.api.create(ObjectKind.DEPLOYMENT, deployment)

        self.controller.reconcile(deployment)

    def run_reconciliation(self) -> None:

        deployments = self.api.list(ObjectKind.DEPLOYMENT)

        for deployment in deployments:
            if isinstance(deployment, Deployment):
                self.controller.reconcile(deployment)

        pending = [
            pod
            for pod in self.api.list(ObjectKind.POD)
            if isinstance(pod, Pod)
            and pod.phase == PodPhase.PENDING
            and pod.node_name is None
        ]

        for pod in pending:
            try:
                self.scheduler.schedule(pod)
            except ConflictError:
                logger.warning(
                    "Concurrent modification detected for %s",
                    pod.name
                )

    def cluster_snapshot(self) -> dict[str, Any]:

        nodes = self.api.list(ObjectKind.NODE)
        pods = self.api.list(ObjectKind.POD)
        deployments = self.api.list(ObjectKind.DEPLOYMENT)

        return {
            "etcd_revision": self.etcd.revision,
            "nodes": [
                {
                    "name": node.name,
                    "condition": node.condition.value,
                    "cpu_used": node.used_cpu,
                    "cpu_capacity": node.allocatable_cpu,
                    "memory_used": node.used_memory,
                    "memory_capacity": node.allocatable_memory
                }
                for node in nodes
                if isinstance(node, Node)
            ],
            "pods": [
                {
                    "name": pod.name,
                    "phase": pod.phase.value,
                    "node": pod.node_name,
                    "owner": pod.owner
                }
                for pod in pods
                if isinstance(pod, Pod)
            ],
            "deployments": [
                {
                    "name": deployment.name,
                    "desired_replicas": deployment.replicas
                }
                for deployment in deployments
                if isinstance(deployment, Deployment)
            ]
        }


# ============================================================
# EXECUTABLE SCENARIO
# ============================================================

def main() -> None:

    cluster = ControlPlane()

    print("\nKUBERNETES CONTROL PLANE SIMULATION")
    print("=" * 55)

    # Register worker nodes.
    cluster.add_node("worker-01", cpu=8, memory=16384)
    cluster.add_node("worker-02", cpu=4, memory=8192)

    # Submit desired application state.
    deployment = Deployment(
        name="web-application",
        replicas=4,
        selector={"app": "web"},
        template_image="nginx:1.27",
        cpu_request=1,
        memory_request=512
    )

    cluster.deploy(deployment)

    # First reconciliation and scheduling cycle.
    cluster.run_reconciliation()

    # Reconcile again to demonstrate idempotent behavior.
    cluster.run_reconciliation()

    snapshot = cluster.cluster_snapshot()

    print("\nCLUSTER SNAPSHOT")
    print(json.dumps(snapshot, indent=2))

    print("\nSCHEDULING EVENTS")
    print(json.dumps(cluster.scheduler.scheduling_events, indent=2))

    # Optimistic concurrency demonstration.
    node = cluster.api.get(
        ObjectKind.NODE,
        "default",
        "worker-01"
    )

    try:
        cluster.api.update(
            ObjectKind.NODE,
            node,
            expected_version=0
        )
    except ConflictError as error:
        print("\nEXPECTED VERSION CONFLICT:", error)

    # Validation failure demonstration.
    try:
        invalid = Pod(
            name="invalid-pod",
            cpu_request=0
        )
        cluster.api.create(ObjectKind.POD, invalid)
    except ValidationError as error:
        print("\nEXPECTED VALIDATION FAILURE:", error)

    print("\nFINAL ETCD REVISION:", cluster.etcd.revision)
    print("AUDIT EVENTS:", len(cluster.api.audit_log))


if __name__ == "__main__":
    main()
