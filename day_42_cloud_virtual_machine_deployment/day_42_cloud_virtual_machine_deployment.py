#!/usr/bin/env python3
"""Executable cloud virtual machine deployment and lifecycle simulation.

The standard-library implementation models image selection, SSH key validation,
security-group rules, instance provisioning, lifecycle transitions, deployment
failures, audit events, and safe teardown without creating real cloud resources.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import secrets
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class DeploymentError(Exception):
    """Base exception for deployment and lifecycle failures."""


class ValidationError(DeploymentError):
    """Raised when deployment configuration violates a rule."""


class StateTransitionError(DeploymentError):
    """Raised when an instance cannot enter the requested state."""


class CloudUnavailableError(DeploymentError):
    """Raised when a simulated cloud operation fails."""


class InstanceState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    TERMINATED = "terminated"
    FAILED = "failed"


class Architecture(str, Enum):
    X86_64 = "x86_64"
    ARM64 = "arm64"


class ImageStatus(str, Enum):
    AVAILABLE = "available"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


@dataclass(frozen=True)
class Image:
    image_id: str
    name: str
    version: str
    architecture: Architecture
    status: ImageStatus
    minimum_disk_gib: int
    owner: str
    trusted: bool = True

    def validate_for(self, architecture: Architecture, disk_gib: int) -> None:
        if self.status != ImageStatus.AVAILABLE:
            raise ValidationError(f"Image {self.image_id} is not available.")
        if not self.trusted:
            raise ValidationError("Image owner is not trusted.")
        if self.architecture != architecture:
            raise ValidationError("Image and machine architectures do not match.")
        if disk_gib < self.minimum_disk_gib:
            raise ValidationError(
                f"Image requires at least {self.minimum_disk_gib} GiB."
            )


@dataclass(frozen=True)
class SSHKey:
    name: str
    public_key: str
    fingerprint: str

    @classmethod
    def from_public_key(cls, name: str, public_key: str) -> "SSHKey":
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}", name):
            raise ValidationError("Invalid SSH key name.")
        fields = public_key.strip().split()
        if len(fields) < 2 or fields[0] not in {
            "ssh-ed25519",
            "ssh-rsa",
            "ecdsa-sha2-nistp256",
        }:
            raise ValidationError("Unsupported or malformed SSH public key.")
        try:
            import base64
            decoded = base64.b64decode(fields[1], validate=True)
        except Exception as exc:
            raise ValidationError("SSH public key is not valid base64.") from exc
        if len(decoded) < 16:
            raise ValidationError("SSH public key payload is too short.")
        fingerprint = hashlib.sha256(decoded).hexdigest()
        return cls(name, public_key.strip(), fingerprint)


@dataclass(frozen=True)
class SecurityRule:
    protocol: str
    port_start: int
    port_end: int
    source_cidr: str
    description: str

    def __post_init__(self) -> None:
        if self.protocol not in {"tcp", "udp", "icmp"}:
            raise ValidationError("Unsupported security-group protocol.")
        if not (0 <= self.port_start <= self.port_end <= 65535):
            raise ValidationError("Invalid port range.")
        try:
            ipaddress.ip_network(self.source_cidr, strict=False)
        except ValueError as exc:
            raise ValidationError("Invalid source CIDR.") from exc
        if not self.description.strip():
            raise ValidationError("Security rules require a description.")

    def permits(self, protocol: str, port: int, source_ip: str) -> bool:
        try:
            address = ipaddress.ip_address(source_ip)
            network = ipaddress.ip_network(self.source_cidr, strict=False)
        except ValueError:
            return False
        return (
            self.protocol == protocol
            and self.port_start <= port <= self.port_end
            and address in network
        )


@dataclass
class SecurityGroup:
    name: str
    inbound_rules: list[SecurityRule] = field(default_factory=list)
    outbound_enabled: bool = True

    def add_rule(self, rule: SecurityRule) -> None:
        if rule not in self.inbound_rules:
            self.inbound_rules.append(rule)

    def allows_ssh(self, source_ip: str) -> bool:
        return any(
            rule.permits("tcp", 22, source_ip)
            for rule in self.inbound_rules
        )

    def validate_ssh_exposure(self) -> None:
        for rule in self.inbound_rules:
            if (
                rule.protocol == "tcp"
                and rule.port_start <= 22 <= rule.port_end
                and ipaddress.ip_network(rule.source_cidr, strict=False).prefixlen
                == 0
            ):
                raise ValidationError(
                    "SSH open to the entire IPv4 or IPv6 internet is prohibited."
                )


@dataclass(frozen=True)
class MachineType:
    name: str
    architecture: Architecture
    vcpus: int
    memory_gib: int
    hourly_cost: float

    def __post_init__(self) -> None:
        if self.vcpus < 1 or self.memory_gib < 1 or self.hourly_cost < 0:
            raise ValidationError("Invalid machine type specifications.")


@dataclass
class AuditEvent:
    event_id: str
    instance_id: str
    action: str
    previous_state: str | None
    current_state: str
    timestamp: str
    details: dict[str, Any]


@dataclass
class VirtualMachine:
    instance_id: str
    name: str
    region: str
    image_id: str
    machine_type: MachineType
    disk_gib: int
    ssh_key_name: str
    security_group_name: str
    tags: dict[str, str]
    state: InstanceState = InstanceState.PENDING
    public_ip: str | None = None
    created_at: str = field(default_factory=lambda: utc_now())
    state_changed_at: str = field(default_factory=lambda: utc_now())
    boot_attempts: int = 0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CloudSimulator:
    """A deterministic deployment model with auditable lifecycle transitions."""

    TRANSITIONS = {
        InstanceState.PENDING: {
            InstanceState.RUNNING,
            InstanceState.FAILED,
            InstanceState.TERMINATED,
        },
        InstanceState.RUNNING: {
            InstanceState.STOPPED,
            InstanceState.TERMINATED,
            InstanceState.FAILED,
        },
        InstanceState.STOPPED: {
            InstanceState.RUNNING,
            InstanceState.TERMINATED,
        },
        InstanceState.FAILED: {InstanceState.TERMINATED},
        InstanceState.TERMINATED: set(),
    }

    def __init__(self) -> None:
        self.images: dict[str, Image] = {}
        self.keys: dict[str, SSHKey] = {}
        self.security_groups: dict[str, SecurityGroup] = {}
        self.instances: dict[str, VirtualMachine] = {}
        self.audit_log: list[AuditEvent] = []

    def register_image(self, image: Image) -> None:
        if image.image_id in self.images:
            raise ValidationError("Image ID already exists.")
        self.images[image.image_id] = image

    def register_key(self, key: SSHKey) -> None:
        existing = self.keys.get(key.name)
        if existing and existing.fingerprint != key.fingerprint:
            raise ValidationError("Key name already refers to another key.")
        self.keys[key.name] = key

    def register_security_group(self, group: SecurityGroup) -> None:
        group.validate_ssh_exposure()
        self.security_groups[group.name] = group

    def _record(
        self,
        vm: VirtualMachine,
        action: str,
        previous: InstanceState | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.audit_log.append(
            AuditEvent(
                event_id=str(uuid.uuid4()),
                instance_id=vm.instance_id,
                action=action,
                previous_state=previous.value if previous else None,
                current_state=vm.state.value,
                timestamp=utc_now(),
                details=details or {},
            )
        )

    def _transition(
        self,
        vm: VirtualMachine,
        target: InstanceState,
        action: str,
    ) -> None:
        if target not in self.TRANSITIONS[vm.state]:
            raise StateTransitionError(
                f"Cannot transition {vm.state.value} to {target.value}."
            )
        previous = vm.state
        vm.state = target
        vm.state_changed_at = utc_now()
        self._record(vm, action, previous)

    def create_instance(
        self,
        name: str,
        region: str,
        image_id: str,
        machine_type: MachineType,
        disk_gib: int,
        ssh_key_name: str,
        security_group_name: str,
        tags: dict[str, str] | None = None,
        fail_boot: bool = False,
    ) -> VirtualMachine:
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9-]{0,39}", name):
            raise ValidationError("Invalid instance name.")
        if not re.fullmatch(r"[a-z]{2}-[a-z]+-[0-9]+", region):
            raise ValidationError("Invalid region identifier.")
        if disk_gib < 1 or disk_gib > 16384:
            raise ValidationError("Disk must be between 1 and 16384 GiB.")
        if image_id not in self.images:
            raise ValidationError("Unknown image ID.")
        if ssh_key_name not in self.keys:
            raise ValidationError("Registered SSH public key is required.")
        if security_group_name not in self.security_groups:
            raise ValidationError("Unknown security group.")
        if any(
            vm.name == name and vm.state != InstanceState.TERMINATED
            for vm in self.instances.values()
        ):
            raise ValidationError("An active instance already uses this name.")

        image = self.images[image_id]
        image.validate_for(machine_type.architecture, disk_gib)
        group = self.security_groups[security_group_name]
        group.validate_ssh_exposure()

        vm = VirtualMachine(
            instance_id=f"vm-{uuid.uuid4().hex[:12]}",
            name=name,
            region=region,
            image_id=image_id,
            machine_type=machine_type,
            disk_gib=disk_gib,
            ssh_key_name=ssh_key_name,
            security_group_name=security_group_name,
            tags=dict(tags or {}),
        )
        self.instances[vm.instance_id] = vm
        self._record(vm, "create_requested", None, {"region": region})

        try:
            vm.boot_attempts += 1
            if fail_boot:
                raise CloudUnavailableError("Simulated image boot failure.")
            # Documentation-only IP allocation; this does not create a public host.
            vm.public_ip = f"192.0.2.{secrets.randbelow(253) + 1}"
            self._transition(vm, InstanceState.RUNNING, "instance_started")
        except CloudUnavailableError as exc:
            self._transition(vm, InstanceState.FAILED, "instance_boot_failed")
            self._record(vm, "failure_details", None, {"error": str(exc)})
        return vm

    def stop(self, instance_id: str) -> None:
        vm = self._get_active(instance_id)
        self._transition(vm, InstanceState.STOPPED, "instance_stopped")
        vm.public_ip = None

    def start(self, instance_id: str) -> None:
        vm = self._get_active(instance_id)
        vm.boot_attempts += 1
        self._transition(vm, InstanceState.RUNNING, "instance_started")
        vm.public_ip = f"192.0.2.{secrets.randbelow(253) + 1}"

    def terminate(self, instance_id: str) -> None:
        vm = self._get_active(instance_id)
        self._transition(vm, InstanceState.TERMINATED, "instance_terminated")
        vm.public_ip = None

    def _get_active(self, instance_id: str) -> VirtualMachine:
        try:
            vm = self.instances[instance_id]
        except KeyError as exc:
            raise ValidationError("Unknown instance ID.") from exc
        if vm.state == InstanceState.TERMINATED:
            raise StateTransitionError("Terminated instances cannot be modified.")
        return vm

    def estimate_monthly_cost(self, instance_id: str, hours: float = 730) -> float:
        vm = self._get_active(instance_id)
        if hours < 0:
            raise ValidationError("Hours cannot be negative.")
        if vm.state != InstanceState.RUNNING:
            return 0.0
        return round(vm.machine_type.hourly_cost * hours, 2)

    def export_audit(self, destination: str | Path) -> None:
        payload = [asdict(event) for event in self.audit_log]
        Path(destination).write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )


def build_demo_cloud() -> CloudSimulator:
    cloud = CloudSimulator()
    cloud.register_image(
        Image(
            image_id="img-ubuntu-2404",
            name="Ubuntu Server",
            version="24.04",
            architecture=Architecture.X86_64,
            status=ImageStatus.AVAILABLE,
            minimum_disk_gib=8,
            owner="trusted-image-publisher",
        )
    )
    cloud.register_image(
        Image(
            image_id="img-legacy",
            name="Legacy Linux",
            version="18.04",
            architecture=Architecture.X86_64,
            status=ImageStatus.DEPRECATED,
            minimum_disk_gib=8,
            owner="trusted-image-publisher",
        )
    )

    # This is a syntactically valid example public key, not a usable private key.
    # Replace it with a genuine public key when adapting the example.
    demo_public_key = (
        "ssh-ed25519 "
        "AAAAC3NzaC1lZDI1NTE5AAAAIGV4YW1wbGVwdWJsaWNrZXlkYXRh "
        "deployment-demo"
    )
    cloud.register_key(SSHKey.from_public_key("deployment-admin", demo_public_key))

    group = SecurityGroup("web-admin")
    group.add_rule(
        SecurityRule("tcp", 22, 22, "203.0.113.10/32", "Administrator SSH")
    )
    group.add_rule(
        SecurityRule("tcp", 443, 443, "0.0.0.0/0", "Public HTTPS")
    )
    cloud.register_security_group(group)
    return cloud


def main() -> None:
    print("Cloud virtual machine deployment simulation")
    cloud = build_demo_cloud()
    machine = MachineType(
        name="general.small",
        architecture=Architecture.X86_64,
        vcpus=2,
        memory_gib=4,
        hourly_cost=0.0416,
    )

    vm = cloud.create_instance(
        name="api-staging",
        region="us-east-1",
        image_id="img-ubuntu-2404",
        machine_type=machine,
        disk_gib=20,
        ssh_key_name="deployment-admin",
        security_group_name="web-admin",
        tags={"environment": "staging", "owner": "platform"},
    )
    print(f"Created {vm.instance_id}: {vm.state.value}")
    print(f"SSH allowed from approved administrator: "
          f"{cloud.security_groups['web-admin'].allows_ssh('203.0.113.10')}")
    print(f"SSH allowed from unapproved address: "
          f"{cloud.security_groups['web-admin'].allows_ssh('198.51.100.25')}")
    print(f"Estimated 730-hour cost: ${cloud.estimate_monthly_cost(vm.instance_id):.2f}")

    cloud.stop(vm.instance_id)
    print(f"After stop: {vm.state.value}; public IP: {vm.public_ip}")
    cloud.start(vm.instance_id)
    print(f"After start: {vm.state.value}; boot attempts: {vm.boot_attempts}")
    cloud.terminate(vm.instance_id)
    print(f"After termination: {vm.state.value}")

    try:
        cloud.start(vm.instance_id)
    except StateTransitionError as exc:
        print(f"Expected lifecycle rejection: {exc}")

    try:
        cloud.images["img-legacy"].validate_for(Architecture.X86_64, 20)
    except ValidationError as exc:
        print(f"Expected image validation failure: {exc}")

    failed_vm = cloud.create_instance(
        name="broken-worker",
        region="us-east-1",
        image_id="img-ubuntu-2404",
        machine_type=machine,
        disk_gib=20,
        ssh_key_name="deployment-admin",
        security_group_name="web-admin",
        fail_boot=True,
    )
    print(f"Failed deployment state: {failed_vm.state.value}")
    print(f"Audit events recorded: {len(cloud.audit_log)}")

    # Export is opt-in so running the demonstration does not create files.
    if "--export-audit" in __import__("sys").argv:
        cloud.export_audit("cloud_deployment_audit.json")
        print("Audit exported to cloud_deployment_audit.json")


if __name__ == "__main__":
    main()
