#!/usr/bin/env python3
"""
Key and Secrets Management
Encryption key lifecycle, rotation, secrets storage, certificate inventory,
access policies, audit events, and integrity verification.

Python 3.10+
Standard-library only.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import uuid

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


# ============================================================
# DOMAIN TYPES
# ============================================================

class KeyType(Enum):
    SYMMETRIC = "symmetric"
    HMAC = "hmac"
    SIGNING = "signing"


class KeyStatus(Enum):
    ACTIVE = "active"
    DECRYPT_ONLY = "decrypt_only"
    ROTATED = "rotated"
    REVOKED = "revoked"
    DESTROYED = "destroyed"


class SecretStatus(Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class CertificateStatus(Enum):
    VALID = "valid"
    EXPIRING = "expiring"
    EXPIRED = "expired"
    REVOKED = "revoked"


class Permission(Enum):
    READ = "read"
    WRITE = "write"
    ROTATE = "rotate"
    REVOKE = "revoke"
    ADMIN = "admin"


class SecurityError(Exception):
    pass


class AccessDenied(SecurityError):
    pass


class KeyNotFound(SecurityError):
    pass


class InvalidState(SecurityError):
    pass


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class EncryptionKey:
    key_id: str
    alias: str
    key_type: KeyType
    algorithm: str
    version: int
    created_at: datetime
    expires_at: datetime
    status: KeyStatus
    fingerprint: str
    material: Optional[bytes] = field(default=None, repr=False)
    previous_key_id: Optional[str] = None

    def public_metadata(self) -> dict:
        return {
            "key_id": self.key_id,
            "alias": self.alias,
            "type": self.key_type.value,
            "algorithm": self.algorithm,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "status": self.status.value,
            "fingerprint": self.fingerprint,
            "previous_key_id": self.previous_key_id,
        }


@dataclass
class Secret:
    secret_id: str
    name: str
    value: str = field(repr=False)
    version: int = 1
    status: SecretStatus = SecretStatus.ACTIVE
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass
class Certificate:
    certificate_id: str
    common_name: str
    issuer: str
    fingerprint: str
    serial_number: str
    not_before: datetime
    not_after: datetime
    revoked: bool = False

    def status(self, now: Optional[datetime] = None) -> CertificateStatus:
        now = now or datetime.now(timezone.utc)

        if self.revoked:
            return CertificateStatus.REVOKED
        if now >= self.not_after:
            return CertificateStatus.EXPIRED
        if now >= self.not_after - timedelta(days=30):
            return CertificateStatus.EXPIRING
        return CertificateStatus.VALID


# ============================================================
# AUDIT LOG
# ============================================================

class AuditLogger:
    def __init__(self):
        self.events = []

    def record(self, actor: str, action: str, resource: str,
               outcome: str = "success"):
        self.events.append({
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "action": action,
            "resource": resource,
            "outcome": outcome,
        })

    def export(self, filename: str):
        path = Path(filename)
        path.write_text(
            json.dumps(self.events, indent=2),
            encoding="utf-8"
        )


# ============================================================
# ACCESS CONTROL
# ============================================================

class AccessController:
    def __init__(self):
        self.permissions: dict[str, set[Permission]] = {}

    def grant(self, principal: str, *permissions: Permission):
        self.permissions.setdefault(principal, set()).update(permissions)

    def revoke(self, principal: str, permission: Permission):
        self.permissions.get(principal, set()).discard(permission)

    def authorize(self, principal: str, permission: Permission):
        granted = self.permissions.get(principal, set())

        if permission not in granted and Permission.ADMIN not in granted:
            raise AccessDenied(
                f"{principal} lacks permission: {permission.value}"
            )


# ============================================================
# KEY MANAGEMENT SERVICE
# ============================================================

class KeyManagementService:
    def __init__(self, audit: AuditLogger, access: AccessController):
        self.keys: dict[str, EncryptionKey] = {}
        self.alias_versions: dict[str, int] = {}
        self.audit = audit
        self.access = access

    @staticmethod
    def fingerprint(material: bytes) -> str:
        return hashlib.sha256(material).hexdigest()

    def create_key(
        self,
        actor: str,
        alias: str,
        key_type: KeyType = KeyType.HMAC,
        algorithm: str = "HMAC-SHA256",
        validity_days: int = 365,
        previous_key_id: Optional[str] = None,
    ) -> EncryptionKey:

        self.access.authorize(actor, Permission.WRITE)

        if not alias or len(alias) > 100:
            raise ValueError("Invalid key alias")

        if validity_days <= 0 or validity_days > 3650:
            raise ValueError("Invalid key validity period")

        if key_type == KeyType.HMAC and algorithm != "HMAC-SHA256":
            raise ValueError("Unsupported HMAC algorithm")

        if key_type == KeyType.SYMMETRIC and algorithm != "AES-256-GCM":
            raise ValueError("Unsupported symmetric algorithm")

        if key_type == KeyType.SIGNING and algorithm != "Ed25519":
            raise ValueError("Unsupported signing algorithm")

        version = self.alias_versions.get(alias, 0) + 1

        # Generate cryptographically strong material.
        material = secrets.token_bytes(32)

        key = EncryptionKey(
            key_id=str(uuid.uuid4()),
            alias=alias,
            key_type=key_type,
            algorithm=algorithm,
            version=version,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc)
                       + timedelta(days=validity_days),
            status=KeyStatus.ACTIVE,
            fingerprint=self.fingerprint(material),
            material=material,
            previous_key_id=previous_key_id,
        )

        self.keys[key.key_id] = key
        self.alias_versions[alias] = version

        self.audit.record(actor, "CREATE_KEY", key.key_id)

        return key

    def get_key(self, actor: str, key_id: str) -> EncryptionKey:
        self.access.authorize(actor, Permission.READ)

        key = self.keys.get(key_id)
        if key is None:
            raise KeyNotFound(key_id)

        if key.status in (KeyStatus.REVOKED, KeyStatus.DESTROYED):
            raise InvalidState("Key is unavailable")

        self.audit.record(actor, "READ_KEY_METADATA", key_id)
        return key

    def rotate_key(self, actor: str, key_id: str) -> EncryptionKey:
        self.access.authorize(actor, Permission.ROTATE)

        old = self.keys.get(key_id)

        if old is None:
            raise KeyNotFound(key_id)

        if old.status != KeyStatus.ACTIVE:
            raise InvalidState("Only active keys can be rotated")

        replacement = self.create_key(
            actor=actor,
            alias=old.alias,
            key_type=old.key_type,
            algorithm=old.algorithm,
            previous_key_id=old.key_id,
        )

        # Old key remains available for controlled historical operations.
        old.status = KeyStatus.DECRYPT_ONLY

        self.audit.record(actor, "ROTATE_KEY", key_id)
        return replacement

    def revoke_key(self, actor: str, key_id: str):
        self.access.authorize(actor, Permission.REVOKE)

        key = self.keys.get(key_id)
        if key is None:
            raise KeyNotFound(key_id)

        if key.status == KeyStatus.DESTROYED:
            raise InvalidState("Destroyed key cannot be modified")

        key.status = KeyStatus.REVOKED
        self.audit.record(actor, "REVOKE_KEY", key_id)

    def destroy_key(self, actor: str, key_id: str):
        self.access.authorize(actor, Permission.ADMIN)

        key = self.keys.get(key_id)
        if key is None:
            raise KeyNotFound(key_id)

        if key.status not in (KeyStatus.REVOKED, KeyStatus.ROTATED):
            raise InvalidState("Revoke or rotate key before destruction")

        key.material = None
        key.status = KeyStatus.DESTROYED

        self.audit.record(actor, "DESTROY_KEY", key_id)

    def create_hmac(self, actor: str, key_id: str, message: bytes) -> str:
        self.access.authorize(actor, Permission.READ)

        key = self.keys.get(key_id)

        if key is None or key.material is None:
            raise KeyNotFound(key_id)

        if key.key_type != KeyType.HMAC:
            raise InvalidState("Key is not an HMAC key")

        if key.status != KeyStatus.ACTIVE:
            raise InvalidState("Key cannot create new signatures")

        if datetime.now(timezone.utc) >= key.expires_at:
            raise InvalidState("Key has expired")

        signature = hmac.new(
            key.material,
            message,
            hashlib.sha256
        ).hexdigest()

        self.audit.record(actor, "CREATE_HMAC", key_id)
        return signature

    def verify_hmac(
        self,
        actor: str,
        key_id: str,
        message: bytes,
        signature: str
    ) -> bool:

        self.access.authorize(actor, Permission.READ)

        key = self.keys.get(key_id)

        if key is None or key.material is None:
            raise KeyNotFound(key_id)

        if key.key_type != KeyType.HMAC:
            raise InvalidState("Key is not an HMAC key")

        if key.status not in (KeyStatus.ACTIVE, KeyStatus.DECRYPT_ONLY):
            raise InvalidState("Key cannot verify signatures")

        if datetime.now(timezone.utc) >= key.expires_at:
            raise InvalidState("Key has expired")

        expected = hmac.new(
            key.material,
            message,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    def inventory(self) -> list[dict]:
        return [
            key.public_metadata()
            for key in self.keys.values()
        ]


# ============================================================
# SECRETS MANAGEMENT
# ============================================================

class SecretsManager:
    def __init__(self, audit: AuditLogger, access: AccessController):
        self.secrets: dict[str, Secret] = {}
        self.audit = audit
        self.access = access

    def create(self, actor: str, name: str, value: str) -> Secret:
        self.access.authorize(actor, Permission.WRITE)

        if not name or len(name) > 150:
            raise ValueError("Invalid secret name")

        if not value:
            raise ValueError("Secret cannot be empty")

        secret = Secret(
            secret_id=str(uuid.uuid4()),
            name=name,
            value=value,
        )

        self.secrets[secret.secret_id] = secret
        self.audit.record(actor, "CREATE_SECRET", secret.secret_id)

        return secret

    def read(self, actor: str, secret_id: str) -> str:
        self.access.authorize(actor, Permission.READ)

        secret = self.secrets.get(secret_id)

        if secret is None or secret.status != SecretStatus.ACTIVE:
            raise KeyNotFound(secret_id)

        self.audit.record(actor, "READ_SECRET", secret_id)
        return secret.value

    def rotate(self, actor: str, secret_id: str, new_value: str):
        self.access.authorize(actor, Permission.WRITE)

        secret = self.secrets.get(secret_id)

        if secret is None or secret.status != SecretStatus.ACTIVE:
            raise KeyNotFound(secret_id)

        if not new_value:
            raise ValueError("New secret cannot be empty")

        secret.value = new_value
        secret.version += 1
        secret.updated_at = datetime.now(timezone.utc)

        self.audit.record(actor, "ROTATE_SECRET", secret_id)

    def disable(self, actor: str, secret_id: str):
        self.access.authorize(actor, Permission.ADMIN)

        secret = self.secrets.get(secret_id)

        if secret is None:
            raise KeyNotFound(secret_id)

        secret.status = SecretStatus.DISABLED
        secret.value = ""

        self.audit.record(actor, "DISABLE_SECRET", secret_id)


# ============================================================
# CERTIFICATE INVENTORY
# ============================================================

class CertificateManager:
    def __init__(self, audit: AuditLogger):
        self.certificates: dict[str, Certificate] = {}
        self.audit = audit

    def register(
        self,
        common_name: str,
        issuer: str,
        serial_number: str,
        fingerprint: str,
        not_before: datetime,
        not_after: datetime,
    ) -> Certificate:

        if not common_name or not issuer:
            raise ValueError("Certificate identity is required")

        if not_before >= not_after:
            raise ValueError("Invalid certificate validity interval")

        if not fingerprint or len(fingerprint) != 64:
            raise ValueError("Expected SHA-256 fingerprint")

        if not serial_number:
            raise ValueError("Serial number is required")

        if any(
            c.fingerprint == fingerprint
            for c in self.certificates.values()
        ):
            raise ValueError("Certificate already registered")

        certificate = Certificate(
            certificate_id=str(uuid.uuid4()),
            common_name=common_name,
            issuer=issuer,
            fingerprint=fingerprint,
            serial_number=serial_number,
            not_before=not_before,
            not_after=not_after,
        )

        self.certificates[certificate.certificate_id] = certificate
        self.audit.record(
            "certificate-service",
            "REGISTER_CERTIFICATE",
            certificate.certificate_id
        )

        return certificate

    def revoke(self, certificate_id: str):
        certificate = self.certificates.get(certificate_id)

        if certificate is None:
            raise KeyNotFound(certificate_id)

        certificate.revoked = True
        self.audit.record(
            "certificate-service",
            "REVOKE_CERTIFICATE",
            certificate_id
        )

    def expiry_report(self) -> list[dict]:
        return [
            {
                "certificate_id": cert.certificate_id,
                "common_name": cert.common_name,
                "status": cert.status().value,
                "expires_at": cert.not_after.isoformat(),
            }
            for cert in self.certificates.values()
        ]


# ============================================================
# INTEGRITY AND POLICY EVALUATION
# ============================================================

def verify_inventory_fingerprints(
    keys: dict[str, EncryptionKey]
) -> bool:
    for key in keys.values():
        if key.material is not None:
            actual = hashlib.sha256(key.material).hexdigest()

            if not hmac.compare_digest(actual, key.fingerprint):
                return False

    return True


def evaluate_key_policy(
    key: EncryptionKey,
    maximum_age_days: int = 365,
) -> dict:

    now = datetime.now(timezone.utc)
    age = (now - key.created_at).days

    violations = []

    if key.status != KeyStatus.ACTIVE:
        violations.append("Key is not active")

    if key.expires_at <= now:
        violations.append("Key has expired")

    if age > maximum_age_days:
        violations.append("Key exceeds maximum age")

    return {
        "key_id": key.key_id,
        "compliant": not violations,
        "violations": violations,
    }


# ============================================================
# EXECUTABLE SCENARIO
# ============================================================

def main():
    audit = AuditLogger()
    access = AccessController()

    access.grant(
        "security-admin",
        Permission.READ,
        Permission.WRITE,
        Permission.ROTATE,
        Permission.REVOKE,
        Permission.ADMIN,
    )

    access.grant("application", Permission.READ, Permission.WRITE)

    kms = KeyManagementService(audit, access)
    secrets_manager = SecretsManager(audit, access)
    certificates = CertificateManager(audit)

    print("\n=== KEY AND SECRETS MANAGEMENT ===")

    # Create a signing-integrity key.
    key = kms.create_key(
        "security-admin",
        "payments-hmac",
        KeyType.HMAC,
        "HMAC-SHA256",
        validity_days=365,
    )

    print("Created key:", key.public_metadata())

    # Demonstrate message authentication.
    message = b"payment=INR:5000;transaction=TXN-1001"

    signature = kms.create_hmac(
        "application",
        key.key_id,
        message
    )

    print("HMAC verification:",
          kms.verify_hmac("application", key.key_id, message, signature))

    # Tampering must invalidate the signature.
    print("Tampered message:",
          kms.verify_hmac(
              "application",
              key.key_id,
              b"payment=INR:9000;transaction=TXN-1001",
              signature
          ))

    # Rotate the key.
    replacement = kms.rotate_key("security-admin", key.key_id)

    print("Replacement version:", replacement.version)
    print("Previous key state:", key.status.value)

    # Historical verification remains possible during retention.
    print("Historical verification:",
          kms.verify_hmac("application", key.key_id, message, signature))

    # Store and rotate an application secret.
    secret = secrets_manager.create(
        "security-admin",
        "database/password",
        secrets.token_urlsafe(32),
    )

    print("Secret identifier:", secret.secret_id)
    print("Secret version:", secret.version)

    secrets_manager.rotate(
        "security-admin",
        secret.secret_id,
        secrets.token_urlsafe(48),
    )

    print("Updated secret version:",
          secret.version)

    # Register certificate inventory metadata.
    certificate = certificates.register(
        common_name="api.example.internal",
        issuer="Example Internal CA",
        serial_number="A100200300",
        fingerprint=hashlib.sha256(
            b"certificate-der-example"
        ).hexdigest(),
        not_before=datetime.now(timezone.utc) - timedelta(days=30),
        not_after=datetime.now(timezone.utc) + timedelta(days=120),
    )

    print("Certificate status:", certificate.status().value)

    # Evaluate governance rules.
    print("Key policy:", evaluate_key_policy(replacement))

    # Access denial demonstration.
    try:
        kms.rotate_key("application", replacement.key_id)
    except AccessDenied as exc:
        print("Expected access denial:", exc)

    print("Inventory integrity:",
          verify_inventory_fingerprints(kms.keys))

    print("Certificate report:", certificates.expiry_report())

    # Audit records contain identifiers, not secret values.
    audit.export("security_audit.json")
    print("Audit events:", len(audit.events))
    print("Audit written to security_audit.json")

    # Basic correctness checks.
    assert kms.verify_hmac(
        "application", key.key_id, message, signature
    )

    assert replacement.version == 2
    assert key.status == KeyStatus.DECRYPT_ONLY
    assert secret.version == 2
    assert verify_inventory_fingerprints(kms.keys)

    print("\nAll demonstration checks passed.")


if __name__ == "__main__":
    main()
