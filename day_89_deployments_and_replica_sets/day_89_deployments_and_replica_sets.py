#!/usr/bin/env python3
"""
Deployments and ReplicaSets
Declarative deployment, replica reconciliation, rolling updates, and rollbacks.

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import copy
import json
import logging
import re
import time
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
logger = logging.getLogger("deployment-controller")


class DeploymentError(Exception):
    pass


class ValidationError(DeploymentError):
    pass


class ReconciliationError(DeploymentError):
    pass


class RolloutError(DeploymentError):
    pass


class DeploymentStatus(str, Enum):
    PROGRESSING = "Progressing"
    AVAILABLE = "Available"
    DEGRADED = "Degraded"
    PAUSED = "Paused"


class PodStatus(str, Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    READY = "Ready"
    FAILED = "Failed"
    TERMINATING = "Terminating"


@dataclass(frozen=True)
class ContainerSpec:
    name: str
    image: str
    port: int = 8080
    cpu_request: str = "100m"
    memory_request: str = "128Mi"

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", self.name):
            raise ValidationError("Invalid container name")

        if not re.fullmatch(
            r"[a-zA-Z0-9][a-zA-Z0-9._/:@-]{0,254}", self.image
        ):
            raise ValidationError("Invalid container image reference")

        if not 1 <= self.port <= 65535:
            raise ValidationError("Invalid container port")


@dataclass(frozen=True)
class DeploymentSpec:
    name: str
    namespace: str
    replicas: int
    container: ContainerSpec
    max_surge: int = 1
    max_unavailable: int = 0
    min_ready_seconds: int = 0
    revision_history_limit: int = 5

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?", self.name):
            raise ValidationError("Invalid deployment name")

        if not re.fullmatch(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?", self.namespace):
            raise ValidationError("Invalid namespace")

        if not 0 <= self.replicas <= 10000:
            raise ValidationError("Replicas must be between 0 and 10000")

        if not 0 <= self.max_surge <= 1000:
            raise ValidationError("Invalid max_surge")

        if not 0 <= self.max_unavailable <= self.replicas:
            raise ValidationError("Invalid max_unavailable")

        if self.min_ready_seconds < 0:
            raise ValidationError("Invalid min_ready_seconds")

        if self.revision_history_limit < 1:
            raise ValidationError("Revision history limit must be positive")

        self.container.validate()


@dataclass
class Pod:
    id: str
    replica_set_id: str
    deployment_name: str
    image: str
    status: PodStatus = PodStatus.PENDING
    ready_since: float | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def set_ready(self) -> None:
        self.status = PodStatus.READY
        self.ready_since = time.monotonic()


@dataclass
class ReplicaSet:
    id: str
    deployment_name: str
    revision: int
    image: str
    desired_replicas: int
    pods: dict[str, Pod] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def ready_replicas(self) -> int:
        return sum(p.status == PodStatus.READY for p in self.pods.values())

    @property
    def available_replicas(self) -> int:
        return self.ready_replicas

    @property
    def active_replicas(self) -> int:
        return sum(
            p.status in (PodStatus.PENDING, PodStatus.RUNNING, PodStatus.READY)
            for p in self.pods.values()
        )


@dataclass
class Deployment:
    spec: DeploymentSpec
    revision: int = 0
    status: DeploymentStatus = DeploymentStatus.PROGRESSING
    replica_sets: dict[str, ReplicaSet] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    paused: bool = False
    conditions: list[str] = field(default_factory=list)

    @property
    def desired_replicas(self) -> int:
        return self.spec.replicas

    @property
    def total_replicas(self) -> int:
        return sum(rs.active_replicas for rs in self.replica_sets.values())

    @property
    def ready_replicas(self) -> int:
        return sum(rs.ready_replicas for rs in self.replica_sets.values())

    @property
    def current_replica_set(self) -> ReplicaSet | None:
        if not self.replica_sets:
            return None
        return max(self.replica_sets.values(), key=lambda rs: rs.revision)


class DeploymentController:
    """
    In-memory declarative controller.

    The controller compares desired state with observed state and
    incrementally reconciles ReplicaSets and Pods.

    Each reconcile operation is bounded. A production Kubernetes
    controller additionally uses API watches, leases, work queues,
    leader election, and persistent API-server state.
    """

    def __init__(self) -> None:
        self.deployments: dict[str, Deployment] = {}
        self.events: list[dict[str, Any]] = []

    @staticmethod
    def _key(name: str, namespace: str) -> str:
        return f"{namespace}/{name}"

    def _event(self, deployment: Deployment, message: str) -> None:
        self.events.append({
            "deployment": self._key(
                deployment.spec.name, deployment.spec.namespace
            ),
            "revision": deployment.revision,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def create(self, spec: DeploymentSpec) -> Deployment:
        spec.validate()
        key = self._key(spec.name, spec.namespace)

        if key in self.deployments:
            raise DeploymentError(f"Deployment already exists: {key}")

        deployment = Deployment(spec=spec)
        self.deployments[key] = deployment

        self._create_revision(deployment, spec.container.image)
        self._event(deployment, "Deployment created")
        self.reconcile(deployment)

        return deployment

    def _create_revision(
        self, deployment: Deployment, image: str
    ) -> ReplicaSet:
        deployment.revision += 1

        rs = ReplicaSet(
            id=str(uuid.uuid4()),
            deployment_name=deployment.spec.name,
            revision=deployment.revision,
            image=image,
            desired_replicas=0,
        )

        deployment.replica_sets[rs.id] = rs

        deployment.history.append({
            "revision": deployment.revision,
            "image": image,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        deployment.history = deployment.history[
            -deployment.spec.revision_history_limit:
        ]

        self._event(
            deployment,
            f"Created ReplicaSet revision {rs.revision} using {image}",
        )

        return rs

    def update(
        self,
        name: str,
        namespace: str,
        image: str | None = None,
        replicas: int | None = None,
    ) -> Deployment:
        deployment = self.get(name, namespace)

        new_image = image or deployment.spec.container.image
        new_replicas = (
            deployment.spec.replicas if replicas is None else replicas
        )

        new_spec = copy.deepcopy(deployment.spec)
        new_spec = DeploymentSpec(
            name=new_spec.name,
            namespace=new_spec.namespace,
            replicas=new_replicas,
            container=ContainerSpec(
                name=new_spec.container.name,
                image=new_image,
                port=new_spec.container.port,
                cpu_request=new_spec.container.cpu_request,
                memory_request=new_spec.container.memory_request,
            ),
            max_surge=new_spec.max_surge,
            max_unavailable=new_spec.max_unavailable,
            min_ready_seconds=new_spec.min_ready_seconds,
            revision_history_limit=new_spec.revision_history_limit,
        )
        new_spec.validate()

        image_changed = new_image != deployment.spec.container.image
        deployment.spec = new_spec

        if image_changed:
            self._create_revision(deployment, new_image)
            self._event(deployment, "Image update initiated")
        else:
            self._event(deployment, "Replica count updated")

        self.reconcile(deployment)
        return deployment

    def get(self, name: str, namespace: str = "default") -> Deployment:
        key = self._key(name, namespace)

        if key not in self.deployments:
            raise DeploymentError(f"Deployment not found: {key}")

        return self.deployments[key]

    def reconcile(self, deployment: Deployment) -> None:
        """
        One bounded reconciliation pass.

        The newest ReplicaSet receives new replicas. Old ReplicaSets
        lose replicas only within max_unavailable constraints.
        """
        if deployment.paused:
            deployment.status = DeploymentStatus.PAUSED
            return

        desired = deployment.desired_replicas
        current = deployment.current_replica_set

        if current is None:
            raise ReconciliationError("No ReplicaSet exists")

        all_sets = sorted(
            deployment.replica_sets.values(),
            key=lambda rs: rs.revision,
            reverse=True,
        )

        current.desired_replicas = desired

        for rs in all_sets[1:]:
            rs.desired_replicas = 0

        total = deployment.total_replicas
        surge_limit = desired + deployment.spec.max_surge

        # Scale up the latest ReplicaSet without exceeding maxSurge.
        if current.active_replicas < desired:
            capacity = max(0, surge_limit - total)
            amount = min(
                desired - current.active_replicas,
                capacity,
            )

            for _ in range(amount):
                pod = Pod(
                    id=str(uuid.uuid4()),
                    replica_set_id=current.id,
                    deployment_name=deployment.spec.name,
                    image=current.image,
                )
                current.pods[pod.id] = pod

            if amount:
                self._event(
                    deployment,
                    f"Scaled revision {current.revision} up by {amount}",
                )

        # Scale down old ReplicaSets while preserving availability.
        minimum_available = max(0, desired - deployment.spec.max_unavailable)

        for rs in all_sets[1:]:
            if rs.active_replicas == 0:
                continue

            removable = min(
                rs.active_replicas,
                max(0, deployment.total_replicas - surge_limit),
            )

            if removable == 0 and deployment.ready_replicas > minimum_available:
                removable = 1

            ready_to_remove = [
                pod for pod in rs.pods.values()
                if pod.status == PodStatus.READY
            ]

            pending_to_remove = [
                pod for pod in rs.pods.values()
                if pod.status == PodStatus.PENDING
            ]

            candidates = pending_to_remove + ready_to_remove

            for pod in candidates[:removable]:
                if (
                    pod.status == PodStatus.READY
                    and deployment.ready_replicas - 1 < minimum_available
                ):
                    continue

                pod.status = PodStatus.TERMINATING
                del rs.pods[pod.id]

            if rs.active_replicas == 0:
                rs.desired_replicas = 0

        self._update_status(deployment)

    def _update_status(self, deployment: Deployment) -> None:
        desired = deployment.desired_replicas
        current = deployment.current_replica_set

        if desired == 0:
            deployment.status = DeploymentStatus.AVAILABLE
            return

        if current is None:
            deployment.status = DeploymentStatus.DEGRADED
            return

        if deployment.ready_replicas >= desired:
            deployment.status = DeploymentStatus.AVAILABLE
        else:
            deployment.status = DeploymentStatus.PROGRESSING

    def mark_pod_ready(
        self,
        deployment_name: str,
        namespace: str,
        replica_set_id: str,
        pod_id: str,
    ) -> None:
        deployment = self.get(deployment_name, namespace)

        try:
            rs = deployment.replica_sets[replica_set_id]
            pod = rs.pods[pod_id]
        except KeyError as exc:
            raise DeploymentError("ReplicaSet or Pod not found") from exc

        if pod.status == PodStatus.FAILED:
            raise DeploymentError("A failed Pod cannot become ready")

        pod.status = PodStatus.RUNNING
        pod.set_ready()

        self._event(deployment, f"Pod {pod.id[:8]} became ready")
        self.reconcile(deployment)

    def mark_pod_failed(
        self,
        deployment_name: str,
        namespace: str,
        replica_set_id: str,
        pod_id: str,
    ) -> None:
        deployment = self.get(deployment_name, namespace)

        try:
            pod = deployment.replica_sets[replica_set_id].pods[pod_id]
        except KeyError as exc:
            raise DeploymentError("Pod not found") from exc

        pod.status = PodStatus.FAILED
        self._event(deployment, f"Pod {pod.id[:8]} failed")

        # Remove failed Pod and allow reconciliation to replace it.
        del deployment.replica_sets[replica_set_id].pods[pod_id]
        self.reconcile(deployment)

    def complete_pending_pods(
        self,
        deployment: Deployment,
        fail_images: set[str] | None = None,
    ) -> None:
        """
        Simulates scheduling, container startup, and readiness probes.
        """
        fail_images = fail_images or set()

        for rs in list(deployment.replica_sets.values()):
            for pod in list(rs.pods.values()):
                if pod.status != PodStatus.PENDING:
                    continue

                if pod.image in fail_images:
                    pod.status = PodStatus.FAILED
                    del rs.pods[pod.id]
                    self._event(
                        deployment,
                        f"Pod startup failed for image {pod.image}",
                    )
                    continue

                pod.status = PodStatus.RUNNING
                pod.set_ready()

        self.reconcile(deployment)

    def rolling_update(
        self,
        name: str,
        namespace: str,
        image: str,
        max_steps: int = 100,
    ) -> Deployment:
        deployment = self.update(name, namespace, image=image)

        for _ in range(max_steps):
            self.complete_pending_pods(deployment)
            self.reconcile(deployment)

            current = deployment.current_replica_set

            if current is None:
                raise RolloutError("Missing current ReplicaSet")

            old_active = sum(
                rs.active_replicas
                for rs in deployment.replica_sets.values()
                if rs.id != current.id
            )

            if (
                current.ready_replicas == deployment.desired_replicas
                and old_active == 0
            ):
                self._event(deployment, "Rolling update completed")
                return deployment

        deployment.status = DeploymentStatus.DEGRADED
        raise RolloutError(
            "Rolling update did not complete within the step limit"
        )

    def rollback(
        self,
        name: str,
        namespace: str,
        target_revision: int | None = None,
    ) -> Deployment:
        deployment = self.get(name, namespace)

        candidates = [
            rs for rs in deployment.replica_sets.values()
            if rs.revision < deployment.revision
            and (
                target_revision is None
                or rs.revision == target_revision
            )
        ]

        if not candidates:
            raise RolloutError("No eligible historical revision")

        target = max(candidates, key=lambda rs: rs.revision)

        deployment.spec = DeploymentSpec(
            name=deployment.spec.name,
            namespace=deployment.spec.namespace,
            replicas=deployment.spec.replicas,
            container=ContainerSpec(
                name=deployment.spec.container.name,
                image=target.image,
                port=deployment.spec.container.port,
                cpu_request=deployment.spec.container.cpu_request,
                memory_request=deployment.spec.container.memory_request,
            ),
            max_surge=deployment.spec.max_surge,
            max_unavailable=deployment.spec.max_unavailable,
            min_ready_seconds=deployment.spec.min_ready_seconds,
            revision_history_limit=deployment.spec.revision_history_limit,
        )

        self._create_revision(deployment, target.image)
        self._event(
            deployment,
            f"Rollback initiated to image {target.image}",
        )

        self.reconcile(deployment)
        return deployment

    def pause(self, name: str, namespace: str) -> None:
        deployment = self.get(name, namespace)
        deployment.paused = True
        deployment.status = DeploymentStatus.PAUSED
        self._event(deployment, "Deployment paused")

    def resume(self, name: str, namespace: str) -> None:
        deployment = self.get(name, namespace)
        deployment.paused = False
        self._event(deployment, "Deployment resumed")
        self.reconcile(deployment)

    def snapshot(self, deployment: Deployment) -> dict[str, Any]:
        return {
            "name": deployment.spec.name,
            "namespace": deployment.spec.namespace,
            "desired_replicas": deployment.desired_replicas,
            "ready_replicas": deployment.ready_replicas,
            "total_replicas": deployment.total_replicas,
            "revision": deployment.revision,
            "image": deployment.spec.container.image,
            "status": deployment.status.value,
            "replica_sets": [
                {
                    "revision": rs.revision,
                    "image": rs.image,
                    "desired": rs.desired_replicas,
                    "active": rs.active_replicas,
                    "ready": rs.ready_replicas,
                }
                for rs in sorted(
                    deployment.replica_sets.values(),
                    key=lambda item: item.revision,
                )
            ],
        }

    def export_events(self, path: str | Path) -> None:
        # Restrict output to an explicitly supplied destination.
        destination = Path(path)
        destination.write_text(
            json.dumps(self.events, indent=2),
            encoding="utf-8",
        )


def run_tests() -> None:
    controller = DeploymentController()

    spec = DeploymentSpec(
        name="inventory-api",
        namespace="production",
        replicas=3,
        container=ContainerSpec(
            name="api",
            image="registry.example.com/inventory:v1",
            port=8080,
        ),
        max_surge=1,
        max_unavailable=0,
    )

    deployment = controller.create(spec)
    assert deployment.ready_replicas == 0

    controller.complete_pending_pods(deployment)
    assert deployment.ready_replicas == 3

    controller.rolling_update(
        "inventory-api",
        "production",
        "registry.example.com/inventory:v2",
    )

    assert deployment.spec.container.image.endswith(":v2")
    assert deployment.ready_replicas == 3
    assert deployment.status == DeploymentStatus.AVAILABLE

    controller.rolling_update(
        "inventory-api",
        "production",
        "registry.example.com/inventory:v3",
    )

    assert deployment.current_replica_set.image.endswith(":v3")

    controller.rollback(
        "inventory-api",
        "production",
        target_revision=2,
    )

    controller.complete_pending_pods(deployment)

    assert deployment.spec.container.image.endswith(":v2")
    assert deployment.ready_replicas == 3

    controller.update(
        "inventory-api",
        "production",
        replicas=5,
    )
    controller.complete_pending_pods(deployment)
    assert deployment.ready_replicas == 5

    controller.update(
        "inventory-api",
        "production",
        replicas=0,
    )
    assert deployment.total_replicas == 0

    try:
        DeploymentSpec(
            name="INVALID NAME",
            namespace="production",
            replicas=-1,
            container=ContainerSpec("api", "invalid image"),
        ).validate()
        raise AssertionError("Invalid deployment was accepted")
    except ValidationError:
        pass

    print("All deployment tests passed.")
    print(json.dumps(controller.snapshot(deployment), indent=2))


def main() -> None:
    controller = DeploymentController()

    deployment = controller.create(
        DeploymentSpec(
            name="payment-service",
            namespace="production",
            replicas=3,
            container=ContainerSpec(
                name="payment-api",
                image="registry.example.com/payment:v1",
            ),
            max_surge=1,
            max_unavailable=0,
        )
    )

    controller.complete_pending_pods(deployment)

    print("\nInitial deployment")
    print(json.dumps(controller.snapshot(deployment), indent=2))

    print("\nRolling update")
    controller.rolling_update(
        "payment-service",
        "production",
        "registry.example.com/payment:v2",
    )
    print(json.dumps(controller.snapshot(deployment), indent=2))

    print("\nRollback")
    controller.rollback(
        "payment-service",
        "production",
        target_revision=1,
    )
    controller.complete_pending_pods(deployment)
    print(json.dumps(controller.snapshot(deployment), indent=2))

    print("\nRunning assertions")
    run_tests()


if __name__ == "__main__":
    main()
