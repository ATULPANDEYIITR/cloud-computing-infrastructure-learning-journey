#!/usr/bin/env python3
"""
CLOUD SECURITY PROJECT
Secure cloud environment using IAM, encryption, network isolation,
centralized logging, security monitoring, and auditing.

Python 3.10+
Standard-library implementation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import sys
import unittest

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


# ============================================================
# CONFIGURATION
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

logger = logging.getLogger("cloud-security")

PROJECT_NAME = "SecureCloud"
AUDIT_FILE = Path("cloud_security_audit.jsonl")


# ============================================================
# DOMAIN ENUMERATIONS
# ============================================================

class Effect(Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class ResourceState(Enum):
    ACTIVE = "ACTIVE"
    ENCRYPTED = "ENCRYPTED"
    BLOCKED = "BLOCKED"
    DELETED = "DELETED"


class Severity(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Environment(Enum):
    DEVELOPMENT = "DEVELOPMENT"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"


# ============================================================
# VALIDATION
# ============================================================

def validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} cannot be empty")

    if len(value) > 128:
        raise ValueError(f"{field_name} exceeds maximum length")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# IAM: IDENTITY AND ACCESS MANAGEMENT
# ============================================================

@dataclass(frozen=True)
class PolicyStatement:
    effect: Effect
    actions: frozenset[str]
    resources: frozenset[str]

    def __post_init__(self):
        if not self.actions or not self.resources:
            raise ValueError("IAM actions and resources are required")


@dataclass
class IAMRole:
    name: str
    statements: list[PolicyStatement] = field(default_factory=list)

    def __post_init__(self):
        validate_identifier(self.name, "Role name")

    def add_statement(self, statement: PolicyStatement) -> None:
        self.statements.append(statement)

    def permits(self, action: str, resource: str) -> bool:
        """
        Explicit DENY overrides ALLOW.
        Wildcards support exact '*' and suffix matching.
        """
        matching_effects = []

        for statement in self.statements:
            action_match = any(
                self._matches(pattern, action)
                for pattern in statement.actions
            )

            resource_match = any(
                self._matches(pattern, resource)
                for pattern in statement.resources
            )

            if action_match and resource_match:
                matching_effects.append(statement.effect)

        if Effect.DENY in matching_effects:
            return False

        return Effect.ALLOW in matching_effects

    @staticmethod
    def _matches(pattern: str, value: str) -> bool:
        if pattern == "*":
            return True

        if pattern.endswith("*"):
            return value.startswith(pattern[:-1])

        return pattern == value


@dataclass
class CloudIdentity:
    identity_id: str
    role: IAMRole
    active: bool = True
    mfa_enabled: bool = False

    def __post_init__(self):
        validate_identifier(self.identity_id, "Identity ID")


class IAMService:

    def __init__(self):
        self.identities: dict[str, CloudIdentity] = {}

    def register(self, identity: CloudIdentity) -> None:
        if identity.identity_id in self.identities:
            raise ValueError("Identity already registered")

        self.identities[identity.identity_id] = identity

    def authorize(
        self,
        identity_id: str,
        action: str,
        resource: str,
        require_mfa: bool = True
    ) -> bool:

        identity = self.identities.get(identity_id)

        if identity is None or not identity.active:
            return False

        if require_mfa and not identity.mfa_enabled:
            return False

        return identity.role.permits(action, resource)


# ============================================================
# ENCRYPTION AND KEY MANAGEMENT
# ============================================================

@dataclass
class EncryptionMetadata:
    key_id: str
    algorithm: str
    encrypted_at: str
    encryption_context: dict[str, str]


class KeyManagementService:
    """
    Demonstration KMS adapter.

    This implementation models key references and encryption metadata.
    It deliberately does not implement cryptography.

    Production deployments must use a managed KMS or HSM and
    authenticated encryption such as AES-256-GCM.
    """

    def __init__(self):
        self.keys: dict[str, dict[str, Any]] = {}

    def create_key(self, alias: str) -> str:
        validate_identifier(alias, "Key alias")

        if alias in self.keys:
            raise ValueError("Key alias already exists")

        key_id = secrets.token_hex(16)

        self.keys[alias] = {
            "key_id": key_id,
            "enabled": True,
            "rotation_version": 1
        }

        return key_id

    def key_enabled(self, key_id: str) -> bool:
        return any(
            key["key_id"] == key_id and key["enabled"]
            for key in self.keys.values()
        )

    def rotate_key(self, alias: str) -> None:
        if alias not in self.keys:
            raise ValueError("Unknown key alias")

        self.keys[alias]["rotation_version"] += 1
        self.keys[alias]["key_id"] = secrets.token_hex(16)

    def disable_key(self, alias: str) -> None:
        if alias not in self.keys:
            raise ValueError("Unknown key alias")

        self.keys[alias]["enabled"] = False


# ============================================================
# CLOUD STORAGE
# ============================================================

@dataclass
class CloudResource:
    resource_id: str
    owner: str
    environment: Environment
    data: str
    state: ResourceState = ResourceState.ACTIVE
    encryption: Optional[EncryptionMetadata] = None

    def __post_init__(self):
        validate_identifier(self.resource_id, "Resource ID")
        validate_identifier(self.owner, "Owner")


class StorageService:

    def __init__(self, kms: KeyManagementService):
        self.kms = kms
        self.resources: dict[str, CloudResource] = {}

    def create(self, resource: CloudResource) -> None:
        if resource.resource_id in self.resources:
            raise ValueError("Resource already exists")

        self.resources[resource.resource_id] = resource

    def encrypt(
        self,
        resource_id: str,
        key_id: str,
        context: Optional[dict[str, str]] = None
    ) -> None:

        resource = self.resources.get(resource_id)

        if resource is None:
            raise ValueError("Resource not found")

        if not self.kms.key_enabled(key_id):
            raise ValueError("Encryption key is unavailable")

        resource.encryption = EncryptionMetadata(
            key_id=key_id,
            algorithm="AES-256-GCM",
            encrypted_at=utc_now(),
            encryption_context=context or {}
        )

        resource.state = ResourceState.ENCRYPTED

    def is_secure(self, resource_id: str) -> bool:
        resource = self.resources.get(resource_id)

        return bool(
            resource
            and resource.state == ResourceState.ENCRYPTED
            and resource.encryption
            and self.kms.key_enabled(resource.encryption.key_id)
        )


# ============================================================
# NETWORK ISOLATION
# ============================================================

@dataclass(frozen=True)
class NetworkRule:
    source: str
    destination: str
    port: int
    protocol: str
    allow: bool

    def __post_init__(self):
        if not 1 <= self.port <= 65535:
            raise ValueError("Invalid network port")

        if self.protocol not in {"TCP", "UDP", "ICMP"}:
            raise ValueError("Unsupported protocol")


class NetworkSecurityGroup:

    def __init__(self, name: str):
        validate_identifier(name, "Network group")

        self.name = name
        self.rules: list[NetworkRule] = []

    def add_rule(self, rule: NetworkRule) -> None:
        self.rules.append(rule)

    def permits(
        self,
        source: str,
        destination: str,
        port: int,
        protocol: str = "TCP"
    ) -> bool:
        """
        Default-deny network policy.
        A matching explicit deny overrides an allow.
        """
        matches = [
            rule for rule in self.rules
            if rule.source in {"*", source}
            and rule.destination in {"*", destination}
            and rule.port == port
            and rule.protocol == protocol
        ]

        if any(not rule.allow for rule in matches):
            return False

        return any(rule.allow for rule in matches)


# ============================================================
# CENTRALIZED AUDIT LOGGING
# ============================================================

@dataclass
class AuditEvent:
    event_id: str
    timestamp: str
    identity: str
    action: str
    resource: str
    result: str
    severity: Severity
    details: dict[str, Any]


class AuditLogger:

    def __init__(self, path: Path = AUDIT_FILE):
        self.path = path
        self.events: list[AuditEvent] = []

    def record(
        self,
        identity: str,
        action: str,
        resource: str,
        result: str,
        severity: Severity = Severity.LOW,
        details: Optional[dict[str, Any]] = None
    ) -> AuditEvent:

        event = AuditEvent(
            event_id=secrets.token_hex(12),
            timestamp=utc_now(),
            identity=identity,
            action=action,
            resource=resource,
            result=result,
            severity=severity,
            details=details or {}
        )

        self.events.append(event)

        # Append-only application behavior. Production audit storage
        # should use immutable, access-controlled centralized storage.
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(asdict(event), default=str) + "\n")

        return event

    def count_by_severity(self) -> dict[str, int]:
        counts = {severity.value: 0 for severity in Severity}

        for event in self.events:
            counts[event.severity.value] += 1

        return counts


# ============================================================
# SECURITY MONITORING
# ============================================================

@dataclass
class SecurityFinding:
    finding_id: str
    category: str
    severity: Severity
    description: str
    resource: str


class SecurityMonitor:

    def evaluate(
        self,
        iam: IAMService,
        storage: StorageService,
        network: NetworkSecurityGroup
    ) -> list[SecurityFinding]:

        findings = []

        for identity in iam.identities.values():
            if identity.active and not identity.mfa_enabled:
                findings.append(SecurityFinding(
                    secrets.token_hex(8),
                    "IAM_MFA",
                    Severity.HIGH,
                    "Active identity does not have MFA enabled",
                    identity.identity_id
                ))

        for resource in storage.resources.values():
            if not storage.is_secure(resource.resource_id):
                findings.append(SecurityFinding(
                    secrets.token_hex(8),
                    "STORAGE_ENCRYPTION",
                    Severity.CRITICAL,
                    "Resource is not protected by an enabled encryption key",
                    resource.resource_id
                ))

        if not network.rules:
            findings.append(SecurityFinding(
                secrets.token_hex(8),
                "NETWORK_POLICY",
                Severity.HIGH,
                "Network security group has no explicit rules",
                network.name
            ))

        return findings


# ============================================================
# CLOUD SECURITY ORCHESTRATOR
# ============================================================

class CloudSecurityPlatform:

    def __init__(self):
        self.iam = IAMService()
        self.kms = KeyManagementService()
        self.storage = StorageService(self.kms)
        self.network = NetworkSecurityGroup("production-vpc")
        self.audit = AuditLogger()
        self.monitor = SecurityMonitor()

    def perform_action(
        self,
        identity_id: str,
        action: str,
        resource_id: str
    ) -> bool:

        authorized = self.iam.authorize(
            identity_id,
            action,
            resource_id
        )

        self.audit.record(
            identity=identity_id,
            action=action,
            resource=resource_id,
            result="ALLOWED" if authorized else "DENIED",
            severity=Severity.LOW if authorized else Severity.HIGH
        )

        return authorized

    def security_report(self) -> dict[str, Any]:

        findings = self.monitor.evaluate(
            self.iam,
            self.storage,
            self.network
        )

        return {
            "project": PROJECT_NAME,
            "generated_at": utc_now(),
            "identities": len(self.iam.identities),
            "resources": len(self.storage.resources),
            "encrypted_resources": sum(
                self.storage.is_secure(resource_id)
                for resource_id in self.storage.resources
            ),
            "network_rules": len(self.network.rules),
            "findings": [asdict(f) for f in findings],
            "audit_severity_counts": self.audit.count_by_severity(),
            "security_status": (
                "COMPLIANT" if not findings else "ACTION_REQUIRED"
            )
        }


# ============================================================
# TESTING
# ============================================================

class CloudSecurityTests(unittest.TestCase):

    def setUp(self):
        self.platform = CloudSecurityPlatform()

        role = IAMRole("storage-reader")

        role.add_statement(PolicyStatement(
            Effect.ALLOW,
            frozenset({"storage:read"}),
            frozenset({"bucket:reports/*"})
        ))

        role.add_statement(PolicyStatement(
            Effect.DENY,
            frozenset({"storage:delete"}),
            frozenset({"*"})
        ))

        self.platform.iam.register(
            CloudIdentity(
                "analyst-01",
                role,
                active=True,
                mfa_enabled=True
            )
        )

    def test_iam_allow(self):
        self.assertTrue(
            self.platform.perform_action(
                "analyst-01",
                "storage:read",
                "bucket:reports/annual"
            )
        )

    def test_iam_explicit_deny(self):
        self.assertFalse(
            self.platform.perform_action(
                "analyst-01",
                "storage:delete",
                "bucket:reports/annual"
            )
        )

    def test_default_deny(self):
        self.assertFalse(
            self.platform.perform_action(
                "analyst-01",
                "storage:admin",
                "bucket:reports/annual"
            )
        )

    def test_encryption(self):
        key_id = self.platform.kms.create_key("production-key")

        self.platform.storage.create(CloudResource(
            "database-backup",
            "security-team",
            Environment.PRODUCTION,
            "sensitive-backup"
        ))

        self.platform.storage.encrypt(
            "database-backup",
            key_id
        )

        self.assertTrue(
            self.platform.storage.is_secure("database-backup")
        )

    def test_network_default_deny(self):
        self.assertFalse(
            self.platform.network.permits(
                "internet",
                "database",
                5432
            )
        )

    def test_network_allow(self):
        self.platform.network.add_rule(NetworkRule(
            "application-subnet",
            "database",
            5432,
            "TCP",
            True
        ))

        self.assertTrue(
            self.platform.network.permits(
                "application-subnet",
                "database",
                5432
            )
        )


# ============================================================
# DEMONSTRATION
# ============================================================

def main():

    platform = CloudSecurityPlatform()

    # IAM configuration
    administrator = IAMRole("cloud-security-admin")

    administrator.add_statement(PolicyStatement(
        Effect.ALLOW,
        frozenset({"storage:read", "storage:write"}),
        frozenset({"bucket:production/*"})
    ))

    platform.iam.register(CloudIdentity(
        "admin-001",
        administrator,
        active=True,
        mfa_enabled=True
    ))

    # Key management
    key_id = platform.kms.create_key("production-storage-key")

    # Storage provisioning
    platform.storage.create(CloudResource(
        resource_id="production-database-backup",
        owner="database-team",
        environment=Environment.PRODUCTION,
        data="confidential-database-backup"
    ))

    platform.storage.encrypt(
        "production-database-backup",
        key_id,
        {"environment": "production"}
    )

    # Network isolation
    platform.network.add_rule(NetworkRule(
        "application-subnet",
        "database-subnet",
        5432,
        "TCP",
        True
    ))

    platform.network.add_rule(NetworkRule(
        "internet",
        "database-subnet",
        5432,
        "TCP",
        False
    ))

    # Authorization and auditing
    platform.perform_action(
        "admin-001",
        "storage:read",
        "bucket:production/reports"
    )

    platform.perform_action(
        "admin-001",
        "storage:delete",
        "bucket:production/reports"
    )

    # Monitoring
    report = platform.security_report()

    print(json.dumps(report, indent=4))

    print("\nRunning security tests...")
    unittest.main(argv=[sys.argv[0]], exit=False)


if __name__ == "__main__":
    main()
