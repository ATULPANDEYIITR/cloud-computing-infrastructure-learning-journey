#!/usr/bin/env python3
"""
Virtual Infrastructure Project
==============================

A self-contained virtual infrastructure management simulator.

Models:
- Virtual machines and lifecycle transitions
- Virtual networks, subnets, and IP allocation
- Storage pools, volumes, and capacity enforcement
- Users, roles, and access control
- Isolated environments and resource quotas
- VM-to-network and VM-to-volume attachments
- Infrastructure validation and deployment planning
- Snapshots, audit events, and infrastructure reporting

Run:
    python virtual_infrastructure.py

Uses only the Python standard library. This is a control-plane simulator,
not a hypervisor driver. It does not create actual operating-system VMs.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import secrets
import threading
import unittest

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
LOGGER = logging.getLogger("virtual-infrastructure")


def utc_now() -> str:
    """Return an unambiguous UTC timestamp for audit records."""
    return datetime.now(timezone.utc).isoformat()


def validate_name(value: str, field_name: str = "name") -> str:
    """Restrict infrastructure identifiers to predictable characters."""
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z][A-Za-z0-9_-]{1,62}", value
    ):
        raise ValueError(
            f"{field_name} must start with a letter and contain "
            "2-63 letters, digits, underscores, or hyphens"
        )
    return value


class InfrastructureError(Exception):
    """Base class for infrastructure management failures."""


class CapacityError(InfrastructureError):
    """Raised when a resource pool cannot satisfy a request."""


class AuthorizationError(InfrastructureError):
    """Raised when a user lacks permission."""


class StateTransitionError(InfrastructureError):
    """Raised when an operation is invalid for the current state."""


class NotFoundError(InfrastructureError):
    """Raised when an infrastructure resource does not exist."""


class VMState(str, Enum):
    PROVISIONING = "provisioning"
    STOPPED = "stopped"
    RUNNING = "running"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class Role(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


class EnvironmentState(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


@dataclass(frozen=True)
class ResourceRequest:
    """Compute resources requested by a virtual machine."""

    vcpus: int
    memory_mb: int

    def __post_init__(self) -> None:
        if isinstance(self.vcpus, bool) or not isinstance(self.vcpus, int):
            raise ValueError("vCPUs must be an integer")
        if isinstance(self.memory_mb, bool) or not isinstance(self.memory_mb, int):
            raise ValueError("Memory must be an integer in MiB")
        if not 1 <= self.vcpus <= 128:
            raise ValueError("vCPUs must be between 1 and 128")
        if not 128 <= self.memory_mb <= 1_048_576:
            raise ValueError("Memory must be between 128 and 1048576 MiB")


@dataclass(frozen=True)
class ResourceQuota:
    """Hard limits for one isolated environment."""

    max_vms: int
    max_vcpus: int
    max_memory_mb: int
    max_storage_gb: int

    def __post_init__(self) -> None:
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in asdict(self).values()
        ):
            raise ValueError("Quota limits must be non-negative integers")


@dataclass
class AuditEvent:
    timestamp: str
    actor: str
    action: str
    resource_type: str
    resource_id: str
    outcome: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class User:
    username: str
    role: Role
    environment_ids: set[str] = field(default_factory=set)
    enabled: bool = True


@dataclass
class VirtualNetwork:
    network_id: str
    environment_id: str
    cidr: str
    gateway: str
    vlan_id: int
    allocated_ips: dict[str, str] = field(default_factory=dict)
    reserved_ips: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        subnet = ipaddress.ip_network(self.cidr, strict=True)
        gateway_ip = ipaddress.ip_address(self.gateway)

        if gateway_ip not in subnet:
            raise ValueError("Gateway must belong to the network subnet")
        if gateway_ip not in subnet.hosts():
            raise ValueError("Gateway must be a usable host address")
        if not 1 <= self.vlan_id <= 4094:
            raise ValueError("VLAN ID must be between 1 and 4094")

        self.cidr = str(subnet)
        self.gateway = str(gateway_ip)
        self.reserved_ips.add(self.gateway)

    def allocate_ip(self, vm_id: str) -> str:
        """Allocate the first usable, unreserved IPv4 address."""
        if vm_id in self.allocated_ips:
            return self.allocated_ips[vm_id]

        subnet = ipaddress.ip_network(self.cidr)
        for candidate in subnet.hosts():
            address = str(candidate)
            if address not in self.reserved_ips and address not in self.allocated_ips.values():
                self.allocated_ips[vm_id] = address
                return address

        raise CapacityError(f"No available addresses in {self.network_id}")

    def release_ip(self, vm_id: str) -> None:
        self.allocated_ips.pop(vm_id, None)


@dataclass
class StoragePool:
    pool_id: str
    environment_id: str
    capacity_gb: int
    used_gb: int = 0
    volumes: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.capacity_gb, bool) or self.capacity_gb < 1:
            raise ValueError("Storage capacity must be positive")

    @property
    def available_gb(self) -> int:
        return self.capacity_gb - self.used_gb

    def allocate(self, volume_id: str, size_gb: int) -> None:
        if volume_id in self.volumes:
            raise InfrastructureError(f"Volume {volume_id} already exists")
        if isinstance(size_gb, bool) or not isinstance(size_gb, int) or size_gb < 1:
            raise ValueError("Volume size must be a positive integer")
        if size_gb > self.available_gb:
            raise CapacityError(
                f"Storage pool {self.pool_id} has {self.available_gb} GiB available"
            )

        self.volumes[volume_id] = size_gb
        self.used_gb += size_gb

    def release(self, volume_id: str) -> None:
        size = self.volumes.pop(volume_id, None)
        if size is not None:
            self.used_gb -= size


@dataclass
class VirtualMachine:
    vm_id: str
    environment_id: str
    name: str
    resources: ResourceRequest
    image: str
    state: VMState = VMState.PROVISIONING
    network_id: str | None = None
    ip_address: str | None = None
    volume_ids: list[str] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def start(self) -> None:
        if self.state not in (VMState.STOPPED, VMState.SUSPENDED):
            raise StateTransitionError(
                f"Cannot start VM {self.vm_id} from {self.state.value}"
            )
        self.state = VMState.RUNNING

    def stop(self) -> None:
        if self.state != VMState.RUNNING:
            raise StateTransitionError(
                f"Cannot stop VM {self.vm_id} from {self.state.value}"
            )
        self.state = VMState.STOPPED

    def suspend(self) -> None:
        if self.state != VMState.RUNNING:
            raise StateTransitionError(
                f"Cannot suspend VM {self.vm_id} from {self.state.value}"
            )
        self.state = VMState.SUSPENDED

    def terminate(self) -> None:
        if self.state == VMState.TERMINATED:
            raise StateTransitionError("VM is already terminated")
        self.state = VMState.TERMINATED


@dataclass
class VirtualVolume:
    volume_id: str
    environment_id: str
    pool_id: str
    size_gb: int
    attached_vm_id: str | None = None
    encrypted: bool = True


@dataclass
class Environment:
    environment_id: str
    name: str
    quota: ResourceQuota
    state: EnvironmentState = EnvironmentState.ACTIVE
    vm_ids: set[str] = field(default_factory=set)
    network_ids: set[str] = field(default_factory=set)
    pool_ids: set[str] = field(default_factory=set)
    storage_budget_used_gb: int = 0


class VirtualInfrastructure:
    """
    In-memory infrastructure control plane.

    An RLock protects mutations in this process. A real distributed control
    plane additionally requires persistent transactions, distributed
    coordination, idempotency keys, and reconciliation with hypervisors.
    """

    def __init__(self) -> None:
        self.environments: dict[str, Environment] = {}
        self.users: dict[str, User] = {}
        self.networks: dict[str, VirtualNetwork] = {}
        self.storage_pools: dict[str, StoragePool] = {}
        self.vms: dict[str, VirtualMachine] = {}
        self.volumes: dict[str, VirtualVolume] = {}
        self.audit_events: list[AuditEvent] = []
        self._lock = threading.RLock()

    def _audit(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        outcome: str,
        **details: Any,
    ) -> None:
        self.audit_events.append(
            AuditEvent(
                timestamp=utc_now(),
                actor=actor,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome=outcome,
                details=details,
            )
        )

    def add_user(self, username: str, role: Role) -> User:
        validate_name(username, "username")
        with self._lock:
            if username in self.users:
                raise InfrastructureError(f"User {username} already exists")
            user = User(username=username, role=role)
            self.users[username] = user
            self._audit(username, "create_user", "user", username, "success")
            return user

    def _authorize(
        self,
        actor: str,
        action: str,
        environment_id: str | None = None,
    ) -> User:
        user = self.users.get(actor)
        if user is None or not user.enabled:
            raise AuthorizationError("Unknown or disabled user")

        permissions = {
            Role.VIEWER: {"read"},
            Role.OPERATOR: {"read", "operate"},
            Role.ADMIN: {"read", "operate", "admin"},
        }
        required = {
            "read": "read",
            "create_environment": "admin",
            "create_network": "admin",
            "create_storage": "admin",
            "create_vm": "operate",
            "start_vm": "operate",
            "stop_vm": "operate",
            "suspend_vm": "operate",
            "terminate_vm": "operate",
            "create_volume": "operate",
            "attach_volume": "operate",
            "delete_volume": "operate",
            "snapshot": "operate",
            "delete_environment": "admin",
        }.get(action)

        if required is None or required not in permissions[user.role]:
            raise AuthorizationError(
                f"Role {user.role.value} cannot perform {action}"
            )

        if environment_id and environment_id not in user.environment_ids:
            if user.role != Role.ADMIN:
                raise AuthorizationError(
                    f"User {actor} has no access to environment {environment_id}"
                )
        return user

    def create_environment(
        self,
        actor: str,
        environment_id: str,
        name: str,
        quota: ResourceQuota,
    ) -> Environment:
        validate_name(environment_id, "environment_id")
        with self._lock:
            self._authorize(actor, "create_environment")
            if environment_id in self.environments:
                raise InfrastructureError("Environment already exists")

            environment = Environment(environment_id, name, quota)
            self.environments[environment_id] = environment
            self.users[actor].environment_ids.add(environment_id)
            self._audit(
                actor, "create_environment", "environment",
                environment_id, "success", quota=asdict(quota)
            )
            return environment

    def grant_environment_access(
        self, actor: str, username: str, environment_id: str
    ) -> None:
        with self._lock:
            self._authorize(actor, "create_environment")
            if username not in self.users:
                raise NotFoundError(f"User {username} does not exist")
            if environment_id not in self.environments:
                raise NotFoundError(f"Environment {environment_id} does not exist")
            self.users[username].environment_ids.add(environment_id)
            self._audit(
                actor, "grant_environment_access", "environment",
                environment_id, "success", username=username
            )

    def _get_environment(self, environment_id: str) -> Environment:
        environment = self.environments.get(environment_id)
        if environment is None:
            raise NotFoundError(f"Environment {environment_id} does not exist")
        if environment.state != EnvironmentState.ACTIVE:
            raise StateTransitionError("Environment is not active")
        return environment

    def create_network(
        self,
        actor: str,
        environment_id: str,
        network_id: str,
        cidr: str,
        gateway: str,
        vlan_id: int,
    ) -> VirtualNetwork:
        validate_name(network_id, "network_id")
        with self._lock:
            self._authorize(actor, "create_network", environment_id)
            environment = self._get_environment(environment_id)

            if network_id in self.networks:
                raise InfrastructureError("Network already exists")
            subnet = ipaddress.ip_network(cidr, strict=True)

            # Prevent overlapping IPv4 or IPv6 subnets across managed networks.
            for existing in self.networks.values():
                if subnet.version == ipaddress.ip_network(existing.cidr).version:
                    if subnet.overlaps(ipaddress.ip_network(existing.cidr)):
                        raise InfrastructureError(
                            f"Network overlaps with {existing.network_id}"
                        )

            network = VirtualNetwork(
                network_id, environment_id, cidr, gateway, vlan_id
            )
            self.networks[network_id] = network
            environment.network_ids.add(network_id)
            self._audit(actor, "create_network", "network", network_id, "success")
            return network

    def create_storage_pool(
        self,
        actor: str,
        environment_id: str,
        pool_id: str,
        capacity_gb: int,
    ) -> StoragePool:
        validate_name(pool_id, "pool_id")
        with self._lock:
            self._authorize(actor, "create_storage", environment_id)
            environment = self._get_environment(environment_id)

            if pool_id in self.storage_pools:
                raise InfrastructureError("Storage pool already exists")
            if environment.storage_budget_used_gb + capacity_gb > environment.quota.max_storage_gb:
                raise CapacityError("Environment storage quota exceeded")

            pool = StoragePool(pool_id, environment_id, capacity_gb)
            self.storage_pools[pool_id] = pool
            environment.pool_ids.add(pool_id)
            environment.storage_budget_used_gb += capacity_gb
            self._audit(
                actor, "create_storage", "storage_pool",
                pool_id, "success", capacity_gb=capacity_gb
            )
            return pool

    def create_vm(
        self,
        actor: str,
        environment_id: str,
        vm_id: str,
        name: str,
        resources: ResourceRequest,
        image: str,
        network_id: str,
        tags: dict[str, str] | None = None,
    ) -> VirtualMachine:
        validate_name(vm_id, "vm_id")
        validate_name(name, "VM name")
        if not image or len(image) > 256 or "\x00" in image:
            raise ValueError("Image reference is invalid")

        with self._lock:
            self._authorize(actor, "create_vm", environment_id)
            environment = self._get_environment(environment_id)

            if vm_id in self.vms:
                raise InfrastructureError("VM ID already exists")
            if network_id not in environment.network_ids:
                raise InfrastructureError(
                    "VM network must belong to the same environment"
                )
            if len(environment.vm_ids) >= environment.quota.max_vms:
                raise CapacityError("VM quota exceeded")

            used_vcpus = sum(
                vm.resources.vcpus
                for vm in self.vms.values()
                if vm.environment_id == environment_id
                and vm.state != VMState.TERMINATED
            )
            used_memory = sum(
                vm.resources.memory_mb
                for vm in self.vms.values()
                if vm.environment_id == environment_id
                and vm.state != VMState.TERMINATED
            )
            if used_vcpus + resources.vcpus > environment.quota.max_vcpus:
                raise CapacityError("vCPU quota exceeded")
            if used_memory + resources.memory_mb > environment.quota.max_memory_mb:
                raise CapacityError("Memory quota exceeded")

            network = self.networks[network_id]
            vm = VirtualMachine(
                vm_id=vm_id,
                environment_id=environment_id,
                name=name,
                resources=resources,
                image=image,
                network_id=network_id,
                tags=dict(tags or {}),
            )

            # Allocate an IP before committing the VM to the registry.
            # Roll back the allocation if any subsequent operation fails.
            try:
                vm.ip_address = network.allocate_ip(vm_id)
                vm.state = VMState.STOPPED
                self.vms[vm_id] = vm
                environment.vm_ids.add(vm_id)
            except Exception:
                network.release_ip(vm_id)
                self.vms.pop(vm_id, None)
                environment.vm_ids.discard(vm_id)
                raise

            self._audit(
                actor, "create_vm", "vm", vm_id, "success",
                environment_id=environment_id,
                vcpus=resources.vcpus,
                memory_mb=resources.memory_mb,
                network_id=network_id,
                ip_address=vm.ip_address,
            )
            return vm

    def _get_vm(self, vm_id: str) -> VirtualMachine:
        vm = self.vms.get(vm_id)
        if vm is None:
            raise NotFoundError(f"VM {vm_id} does not exist")
        return vm

    def start_vm(self, actor: str, vm_id: str) -> None:
        with self._lock:
            vm = self._get_vm(vm_id)
            self._authorize(actor, "start_vm", vm.environment_id)
            vm.start()
            self._audit(actor, "start_vm", "vm", vm_id, "success")

    def stop_vm(self, actor: str, vm_id: str) -> None:
        with self._lock:
            vm = self._get_vm(vm_id)
            self._authorize(actor, "stop_vm", vm.environment_id)
            vm.stop()
            self._audit(actor, "stop_vm", "vm", vm_id, "success")

    def suspend_vm(self, actor: str, vm_id: str) -> None:
        with self._lock:
            vm = self._get_vm(vm_id)
            self._authorize(actor, "suspend_vm", vm.environment_id)
            vm.suspend()
            self._audit(actor, "suspend_vm", "vm", vm_id, "success")

    def terminate_vm(self, actor: str, vm_id: str) -> None:
        with self._lock:
            vm = self._get_vm(vm_id)
            self._authorize(actor, "terminate_vm", vm.environment_id)

            if vm.state == VMState.TERMINATED:
                raise StateTransitionError("VM is already terminated")

            for volume_id in vm.volume_ids:
                volume = self.volumes.get(volume_id)
                if volume:
                    volume.attached_vm_id = None

            if vm.network_id:
                self.networks[vm.network_id].release_ip(vm_id)

            vm.ip_address = None
            vm.terminate()
            self._audit(actor, "terminate_vm", "vm", vm_id, "success")

    def create_volume(
        self,
        actor: str,
        environment_id: str,
        volume_id: str,
        pool_id: str,
        size_gb: int,
    ) -> VirtualVolume:
        validate_name(volume_id, "volume_id")
        with self._lock:
            self._authorize(actor, "create_volume", environment_id)
            environment = self._get_environment(environment_id)

            if volume_id in self.volumes:
                raise InfrastructureError("Volume already exists")
            if pool_id not in environment.pool_ids:
                raise InfrastructureError(
                    "Storage pool must belong to the same environment"
                )

            pool = self.storage_pools[pool_id]
            if environment.storage_budget_used_gb + size_gb > environment.quota.max_storage_gb:
                raise CapacityError("Environment storage quota exceeded")

            pool.allocate(volume_id, size_gb)
            try:
                volume = VirtualVolume(
                    volume_id, environment_id, pool_id, size_gb
                )
                self.volumes[volume_id] = volume
                environment.storage_budget_used_gb += size_gb
            except Exception:
                pool.release(volume_id)
                raise

            self._audit(
                actor, "create_volume", "volume", volume_id, "success",
                size_gb=size_gb, pool_id=pool_id
            )
            return volume

    def attach_volume(
        self, actor: str, vm_id: str, volume_id: str
    ) -> None:
        with self._lock:
            vm = self._get_vm(vm_id)
            self._authorize(actor, "attach_volume", vm.environment_id)
            volume = self.volumes.get(volume_id)
            if volume is None:
                raise NotFoundError(f"Volume {volume_id} does not exist")
            if volume.environment_id != vm.environment_id:
                raise AuthorizationError(
                    "Cross-environment volume attachment is prohibited"
                )
            if vm.state == VMState.TERMINATED:
                raise StateTransitionError("Cannot attach to a terminated VM")
            if volume.attached_vm_id is not None:
                raise InfrastructureError("Volume is already attached")

            volume.attached_vm_id = vm_id
            vm.volume_ids.append(volume_id)
            self._audit(
                actor, "attach_volume", "volume", volume_id, "success",
                vm_id=vm_id
            )

    def delete_volume(self, actor: str, volume_id: str) -> None:
        with self._lock:
            volume = self.volumes.get(volume_id)
            if volume is None:
                raise NotFoundError(f"Volume {volume_id} does not exist")
            self._authorize(actor, "delete_volume", volume.environment_id)

            if volume.attached_vm_id is not None:
                raise StateTransitionError("Detach the volume before deletion")

            pool = self.storage_pools[volume.pool_id]
            environment = self.environments[volume.environment_id]
            pool.release(volume_id)
            environment.storage_budget_used_gb -= volume.size_gb
            del self.volumes[volume_id]

            self._audit(actor, "delete_volume", "volume", volume_id, "success")

    def create_snapshot_manifest(
        self, actor: str, vm_id: str, destination: str
    ) -> dict[str, Any]:
        """Create a metadata manifest; no disk data is actually copied."""
        with self._lock:
            vm = self._get_vm(vm_id)
            self._authorize(actor, "snapshot", vm.environment_id)
            if vm.state == VMState.TERMINATED:
                raise StateTransitionError("Cannot snapshot a terminated VM")

            manifest = {
                "snapshot_id": secrets.token_hex(12),
                "vm_id": vm.vm_id,
                "captured_at": utc_now(),
                "state": vm.state.value,
                "image": vm.image,
                "resources": asdict(vm.resources),
                "network_id": vm.network_id,
                "volume_ids": list(vm.volume_ids),
                "tags": dict(vm.tags),
                "consistency": (
                    "crash-consistent metadata only; guest quiescing not performed"
                ),
            }

            output_path = Path(destination)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
            try:
                temporary_path.write_text(
                    json.dumps(manifest, indent=2), encoding="utf-8"
                )
                temporary_path.replace(output_path)
            except OSError:
                temporary_path.unlink(missing_ok=True)
                raise

            self._audit(
                actor, "snapshot", "vm", vm_id, "success",
                snapshot_id=manifest["snapshot_id"]
            )
            return manifest

    def inventory(self, actor: str, environment_id: str) -> dict[str, Any]:
        with self._lock:
            self._authorize(actor, "read", environment_id)
            environment = self._get_environment(environment_id)
            vms = [
                self.vms[vm_id]
                for vm_id in sorted(environment.vm_ids)
                if self.vms[vm_id].state != VMState.TERMINATED
            ]
            pools = [
                self.storage_pools[pool_id]
                for pool_id in sorted(environment.pool_ids)
            ]
            return {
                "environment": environment.name,
                "environment_id": environment_id,
                "vm_count": len(vms),
                "running_vms": sum(vm.state == VMState.RUNNING for vm in vms),
                "allocated_vcpus": sum(vm.resources.vcpus for vm in vms),
                "allocated_memory_mb": sum(vm.resources.memory_mb for vm in vms),
                "storage_pool_capacity_gb": sum(pool.capacity_gb for pool in pools),
                "storage_used_gb": sum(pool.used_gb for pool in pools),
                "vms": [
                    {
                        "id": vm.vm_id,
                        "name": vm.name,
                        "state": vm.state.value,
                        "ip": vm.ip_address,
                        "network": vm.network_id,
                        "volumes": list(vm.volume_ids),
                    }
                    for vm in vms
                ],
            }

    def validate_invariants(self) -> list[str]:
        """Check accounting and isolation invariants across the control plane."""
        errors: list[str] = []

        for environment_id, environment in self.environments.items():
            live_vms = [
                self.vms[vm_id]
                for vm_id in environment.vm_ids
                if self.vms[vm_id].state != VMState.TERMINATED
            ]
            if len(live_vms) > environment.quota.max_vms:
                errors.append(f"{environment_id}: VM quota exceeded")
            if sum(vm.resources.vcpus for vm in live_vms) > environment.quota.max_vcpus:
                errors.append(f"{environment_id}: vCPU quota exceeded")
            if sum(vm.resources.memory_mb for vm in live_vms) > environment.quota.max_memory_mb:
                errors.append(f"{environment_id}: memory quota exceeded")

            expected_storage = sum(
                self.storage_pools[pool_id].capacity_gb
                for pool_id in environment.pool_ids
            ) + sum(
                volume.size_gb
                for volume in self.volumes.values()
                if volume.environment_id == environment_id
            )
            if expected_storage != environment.storage_budget_used_gb:
                errors.append(f"{environment_id}: storage budget accounting mismatch")

        for pool in self.storage_pools.values():
            if pool.used_gb != sum(pool.volumes.values()):
                errors.append(f"{pool.pool_id}: storage accounting mismatch")
            if pool.used_gb > pool.capacity_gb:
                errors.append(f"{pool.pool_id}: physical capacity exceeded")

        for vm in self.vms.values():
            if vm.state != VMState.TERMINATED:
                if vm.network_id not in self.networks:
                    errors.append(f"{vm.vm_id}: missing network")
                elif vm.ip_address != self.networks[vm.network_id].allocated_ips.get(vm.vm_id):
                    errors.append(f"{vm.vm_id}: IP allocation mismatch")

            for volume_id in vm.volume_ids:
                volume = self.volumes.get(volume_id)
                if volume is None:
                    errors.append(f"{vm.vm_id}: missing attached volume {volume_id}")
                elif volume.attached_vm_id != vm.vm_id:
                    errors.append(f"{volume_id}: attachment mismatch")

        for volume in self.volumes.values():
            if volume.attached_vm_id:
                vm = self.vms.get(volume.attached_vm_id)
                if vm is None or volume.volume_id not in vm.volume_ids:
                    errors.append(f"{volume.volume_id}: reverse attachment mismatch")

        return errors


def demonstration() -> VirtualInfrastructure:
    infra = VirtualInfrastructure()

    infra.add_user("platform_admin", Role.ADMIN)
    infra.add_user("developer", Role.OPERATOR)
    infra.add_user("auditor", Role.VIEWER)

    infra.create_environment(
        "platform_admin",
        "development",
        "Development Sandbox",
        ResourceQuota(
            max_vms=10,
            max_vcpus=32,
            max_memory_mb=65536,
            max_storage_gb=500,
        ),
    )
    infra.grant_environment_access("platform_admin", "developer", "development")
    infra.grant_environment_access("platform_admin", "auditor", "development")

    infra.create_network(
        "platform_admin", "development", "dev_net",
        "10.20.1.0/24", "10.20.1.1", 120
    )
    infra.create_storage_pool(
        "platform_admin", "development", "dev_pool", 300
    )

    vm = infra.create_vm(
        "developer",
        "development",
        "dev_api_01",
        "Development API",
        ResourceRequest(vcpus=4, memory_mb=8192),
        "ubuntu-24.04",
        "dev_net",
        tags={"application": "api", "owner": "engineering"},
    )

    volume = infra.create_volume(
        "developer", "development", "dev_api_disk", "dev_pool", 40
    )
    infra.attach_volume("developer", vm.vm_id, volume.volume_id)
    infra.start_vm("developer", vm.vm_id)

    print("Infrastructure inventory:")
    print(json.dumps(infra.inventory("auditor", "development"), indent=2))

    print("\nInvariant validation:")
    errors = infra.validate_invariants()
    print("PASS" if not errors else "\n".join(errors))

    print("\nAudit events:", len(infra.audit_events))
    return infra


class InfrastructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.infra = VirtualInfrastructure()
        self.infra.add_user("admin_user", Role.ADMIN)
        self.infra.add_user("operator_user", Role.OPERATOR)
        self.infra.add_user("viewer_user", Role.VIEWER)

        self.infra.create_environment(
            "admin_user", "test_env", "Test Environment",
            ResourceQuota(3, 8, 8192, 100)
        )
        self.infra.grant_environment_access(
            "admin_user", "operator_user", "test_env"
        )
        self.infra.grant_environment_access(
            "admin_user", "viewer_user", "test_env"
        )
        self.infra.create_network(
            "admin_user", "test_env", "test_net",
            "192.168.50.0/24", "192.168.50.1", 200
        )
        self.infra.create_storage_pool(
            "admin_user", "test_env", "test_pool", 80
        )

    def create_test_vm(self, vm_id: str = "test_vm") -> VirtualMachine:
        return self.infra.create_vm(
            "operator_user", "test_env", vm_id, "Test VM",
            ResourceRequest(2, 2048), "debian-12", "test_net"
        )

    def test_vm_lifecycle(self) -> None:
        vm = self.create_test_vm()
        self.assertEqual(vm.state, VMState.STOPPED)
        self.infra.start_vm("operator_user", vm.vm_id)
        self.assertEqual(vm.state, VMState.RUNNING)
        self.infra.stop_vm("operator_user", vm.vm_id)
        self.assertEqual(vm.state, VMState.STOPPED)

    def test_invalid_transition(self) -> None:
        vm = self.create_test_vm()
        with self.assertRaises(StateTransitionError):
            self.infra.stop_vm("operator_user", vm.vm_id)

    def test_viewer_cannot_create_vm(self) -> None:
        with self.assertRaises(AuthorizationError):
            self.infra.create_vm(
                "viewer_user", "test_env", "unauthorized_vm", "Unauthorized",
                ResourceRequest(1, 1024), "debian-12", "test_net"
            )

    def test_overlapping_network_rejected(self) -> None:
        with self.assertRaises(InfrastructureError):
            self.infra.create_network(
                "admin_user", "test_env", "overlap_net",
                "192.168.50.128/25", "192.168.50.129", 201
            )

    def test_vm_quota_enforced(self) -> None:
        self.create_test_vm("vm_one")
        self.create_test_vm("vm_two")
        self.create_test_vm("vm_three")
        with self.assertRaises(CapacityError):
            self.create_test_vm("vm_four")

    def test_storage_capacity_enforced(self) -> None:
        self.infra.create_volume(
            "operator_user", "test_env", "disk_a", "test_pool", 60
        )
        with self.assertRaises(CapacityError):
            self.infra.create_volume(
                "operator_user", "test_env", "disk_b", "test_pool", 30
            )

    def test_cross_environment_attachment_rejected(self) -> None:
        self.infra.create_environment(
            "admin_user", "other_env", "Other Environment",
            ResourceQuota(2, 4, 4096, 100)
        )
        self.infra.create_network(
            "admin_user", "other_env", "other_net",
            "192.168.60.0/24", "192.168.60.1", 201
        )
        self.infra.create_storage_pool(
            "admin_user", "other_env", "other_pool", 50
        )
        self.infra.create_vm(
            "admin_user", "other_env", "other_vm", "Other VM",
            ResourceRequest(1, 1024), "debian-12", "other_net"
        )
        volume = self.infra.create_volume(
            "operator_user", "test_env", "test_disk", "test_pool", 10
        )
        with self.assertRaises(AuthorizationError):
            self.infra.attach_volume("admin_user", "other_vm", volume.volume_id)

    def test_terminated_vm_releases_ip(self) -> None:
        vm = self.create_test_vm()
        old_ip = vm.ip_address
        self.infra.terminate_vm("operator_user", vm.vm_id)
        replacement = self.create_test_vm("replacement_vm")
        self.assertEqual(replacement.ip_address, old_ip)

    def test_invariants(self) -> None:
        self.create_test_vm()
        self.assertEqual(self.infra.validate_invariants(), [])


if __name__ == "__main__":
    infrastructure = demonstration()
    print("\nRunning infrastructure tests...")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(InfrastructureTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
