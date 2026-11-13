#!/usr/bin/env python3
"""
Cloud Governance and Compliance Management System

Demonstrates:
- Cloud resource inventory and ownership
- Policy definition and evaluation
- Regulatory compliance assessment
- Data residency enforcement
- Encryption and access governance
- Audit event recording
- Risk scoring and remediation
- Compliance reporting
- JSON persistence and validation

Python 3.10+
Standard-library only.
"""

from __future__ import annotations

import json
import logging
import hashlib
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("cloud_governance")


# ============================================================
# ENUMERATIONS
# ============================================================

class ResourceType(Enum):
    STORAGE = "storage"
    DATABASE = "database"
    COMPUTE = "compute"
    NETWORK = "network"


class ComplianceStatus(Enum):
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Severity(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class AuditAction(Enum):
    RESOURCE_REGISTERED = "RESOURCE_REGISTERED"
    POLICY_EVALUATED = "POLICY_EVALUATED"
    VIOLATION_DETECTED = "VIOLATION_DETECTED"
    REMEDIATION_APPLIED = "REMEDIATION_APPLIED"
    ACCESS_DENIED = "ACCESS_DENIED"


class DataClassification(Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


# ============================================================
# DOMAIN EXCEPTIONS
# ============================================================

class GovernanceError(Exception):
    """Base exception for governance operations."""


class ValidationError(GovernanceError):
    """Invalid resource or policy configuration."""


class ResourceNotFoundError(GovernanceError):
    """Requested cloud resource does not exist."""


class PolicyViolationError(GovernanceError):
    """A governance rule has been violated."""


class AccessDeniedError(GovernanceError):
    """An operation is not authorized."""


# ============================================================
# DOMAIN MODELS
# ============================================================

@dataclass
class CloudResource:
    resource_id: str
    name: str
    resource_type: ResourceType
    provider: str
    region: str
    data_classification: DataClassification
    owner: str
    encrypted: bool
    public_access: bool
    backup_enabled: bool
    tags: dict[str, str] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def validate(self) -> None:
        if not self.resource_id or not self.name:
            raise ValidationError("Resource ID and name are required.")

        if not self.owner.strip():
            raise ValidationError("Resource owner is required.")

        if not self.region.strip():
            raise ValidationError("Resource region is required.")

        if not self.provider.strip():
            raise ValidationError("Cloud provider is required.")

        if self.resource_type == ResourceType.DATABASE:
            if self.public_access:
                logger.warning(
                    "Database %s has public access enabled.",
                    self.resource_id
                )


@dataclass(frozen=True)
class GovernancePolicy:
    policy_id: str
    name: str
    description: str
    severity: Severity
    required_encryption: bool = False
    prohibit_public_access: bool = False
    required_backup: bool = False
    allowed_regions: tuple[str, ...] = ()
    applicable_classifications: tuple[
        DataClassification, ...
    ] = ()

    def applies_to(self, resource: CloudResource) -> bool:
        return (
            not self.applicable_classifications
            or resource.data_classification
            in self.applicable_classifications
        )


@dataclass
class PolicyResult:
    resource_id: str
    policy_id: str
    status: ComplianceStatus
    severity: Severity
    violations: list[str]
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class AuditEvent:
    event_id: str
    action: AuditAction
    actor: str
    resource_id: str
    details: dict[str, Any]
    timestamp: str
    previous_hash: str
    event_hash: str


# ============================================================
# AUDIT LOG
# ============================================================

class AuditLogger:
    """
    Hash-linked audit records.

    This detects modifications to records within the chain.
    Production systems should additionally use immutable,
    access-controlled external audit storage.
    """

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(
        self,
        action: AuditAction,
        actor: str,
        resource_id: str,
        details: dict[str, Any]
    ) -> AuditEvent:

        previous_hash = (
            self.events[-1].event_hash
            if self.events else "GENESIS"
        )

        timestamp = datetime.now(timezone.utc).isoformat()

        payload = {
            "action": action.value,
            "actor": actor,
            "resource_id": resource_id,
            "details": details,
            "timestamp": timestamp,
            "previous_hash": previous_hash
        }

        serialized = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":")
        )

        event_hash = hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest()

        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            action=action,
            actor=actor,
            resource_id=resource_id,
            details=details,
            timestamp=timestamp,
            previous_hash=previous_hash,
            event_hash=event_hash
        )

        self.events.append(event)
        return event

    def verify_integrity(self) -> bool:
        previous_hash = "GENESIS"

        for event in self.events:
            if event.previous_hash != previous_hash:
                return False

            payload = {
                "action": event.action.value,
                "actor": event.actor,
                "resource_id": event.resource_id,
                "details": event.details,
                "timestamp": event.timestamp,
                "previous_hash": event.previous_hash
            }

            serialized = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":")
            )

            calculated = hashlib.sha256(
                serialized.encode("utf-8")
            ).hexdigest()

            if calculated != event.event_hash:
                return False

            previous_hash = event.event_hash

        return True


# ============================================================
# DATA RESIDENCY GOVERNANCE
# ============================================================

class DataResidencyPolicy:

    def __init__(
        self,
        regulation: str,
        permitted_regions: set[str]
    ) -> None:

        if not regulation:
            raise ValidationError("Regulation name is required.")

        if not permitted_regions:
            raise ValidationError(
                "At least one permitted region is required."
            )

        self.regulation = regulation
        self.permitted_regions = frozenset(permitted_regions)

    def evaluate(self, resource: CloudResource) -> bool:
        return resource.region in self.permitted_regions


# ============================================================
# POLICY ENGINE
# ============================================================

class PolicyEngine:

    def __init__(self, policies: list[GovernancePolicy]):
        self.policies = policies

        policy_ids = [p.policy_id for p in policies]

        if len(policy_ids) != len(set(policy_ids)):
            raise ValidationError("Duplicate policy identifiers.")

    def evaluate(
        self,
        resource: CloudResource
    ) -> list[PolicyResult]:

        resource.validate()
        results: list[PolicyResult] = []

        for policy in self.policies:

            if not policy.applies_to(resource):
                results.append(
                    PolicyResult(
                        resource.resource_id,
                        policy.policy_id,
                        ComplianceStatus.NOT_APPLICABLE,
                        policy.severity,
                        []
                    )
                )
                continue

            violations: list[str] = []

            if (
                policy.required_encryption
                and not resource.encrypted
            ):
                violations.append("Encryption is required.")

            if (
                policy.prohibit_public_access
                and resource.public_access
            ):
                violations.append(
                    "Public access is prohibited."
                )

            if (
                policy.required_backup
                and not resource.backup_enabled
            ):
                violations.append("Backup is required.")

            if (
                policy.allowed_regions
                and resource.region not in policy.allowed_regions
            ):
                violations.append(
                    f"Region {resource.region} is not permitted."
                )

            status = (
                ComplianceStatus.NON_COMPLIANT
                if violations
                else ComplianceStatus.COMPLIANT
            )

            results.append(
                PolicyResult(
                    resource.resource_id,
                    policy.policy_id,
                    status,
                    policy.severity,
                    violations
                )
            )

        return results


# ============================================================
# GOVERNANCE SERVICE
# ============================================================

class GovernanceService:

    def __init__(
        self,
        engine: PolicyEngine,
        audit: AuditLogger
    ) -> None:

        self.engine = engine
        self.audit = audit

        self.resources: dict[str, CloudResource] = {}
        self.results: dict[str, list[PolicyResult]] = {}

    def register_resource(
        self,
        resource: CloudResource,
        actor: str
    ) -> None:

        resource.validate()

        if resource.resource_id in self.resources:
            raise ValidationError(
                "Resource identifier already exists."
            )

        self.resources[resource.resource_id] = resource

        self.audit.record(
            AuditAction.RESOURCE_REGISTERED,
            actor,
            resource.resource_id,
            {"name": resource.name}
        )

    def get_resource(
        self,
        resource_id: str
    ) -> CloudResource:

        if resource_id not in self.resources:
            raise ResourceNotFoundError(resource_id)

        return self.resources[resource_id]

    def evaluate_resource(
        self,
        resource_id: str,
        actor: str
    ) -> list[PolicyResult]:

        resource = self.get_resource(resource_id)

        results = self.engine.evaluate(resource)
        self.results[resource_id] = results

        non_compliant = [
            result for result in results
            if result.status == ComplianceStatus.NON_COMPLIANT
        ]

        self.audit.record(
            AuditAction.POLICY_EVALUATED,
            actor,
            resource_id,
            {
                "policy_count": len(results),
                "violations": sum(
                    len(r.violations) for r in non_compliant
                )
            }
        )

        for result in non_compliant:
            self.audit.record(
                AuditAction.VIOLATION_DETECTED,
                actor,
                resource_id,
                {
                    "policy_id": result.policy_id,
                    "severity": result.severity.name,
                    "violations": result.violations
                }
            )

        return results

    def remediate(
        self,
        resource_id: str,
        actor: str,
        encrypt: bool = False,
        disable_public_access: bool = False,
        enable_backup: bool = False
    ) -> None:

        resource = self.get_resource(resource_id)

        # Apply only explicitly authorized remediation actions.
        if encrypt:
            resource.encrypted = True

        if disable_public_access:
            resource.public_access = False

        if enable_backup:
            resource.backup_enabled = True

        self.audit.record(
            AuditAction.REMEDIATION_APPLIED,
            actor,
            resource_id,
            {
                "encryption": encrypt,
                "public_access_disabled": disable_public_access,
                "backup_enabled": enable_backup
            }
        )

    def report(self) -> dict[str, Any]:

        all_results = [
            result
            for results in self.results.values()
            for result in results
        ]

        applicable = [
            r for r in all_results
            if r.status != ComplianceStatus.NOT_APPLICABLE
        ]

        compliant = [
            r for r in applicable
            if r.status == ComplianceStatus.COMPLIANT
        ]

        violations = [
            r for r in applicable
            if r.status == ComplianceStatus.NON_COMPLIANT
        ]

        compliance_percentage = (
            round(len(compliant) / len(applicable) * 100, 2)
            if applicable else 100.0
        )

        return {
            "resource_count": len(self.resources),
            "evaluated_policy_count": len(all_results),
            "applicable_policy_count": len(applicable),
            "compliant_count": len(compliant),
            "non_compliant_count": len(violations),
            "compliance_percentage": compliance_percentage,
            "critical_violations": sum(
                r.severity == Severity.CRITICAL
                for r in violations
            )
        }

    def export_report(self, filepath: str) -> None:

        report = self.report()

        with Path(filepath).open(
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                report,
                file,
                indent=4
            )


# ============================================================
# CLOUD GOVERNANCE DEMONSTRATION
# ============================================================

def build_policies() -> list[GovernancePolicy]:

    sensitive = (
        DataClassification.CONFIDENTIAL,
        DataClassification.RESTRICTED
    )

    return [
        GovernancePolicy(
            policy_id="POL-001",
            name="Encryption at Rest",
            description="Sensitive resources must be encrypted.",
            severity=Severity.CRITICAL,
            required_encryption=True,
            applicable_classifications=sensitive
        ),
        GovernancePolicy(
            policy_id="POL-002",
            name="Public Exposure Prevention",
            description="Sensitive resources cannot be public.",
            severity=Severity.CRITICAL,
            prohibit_public_access=True,
            applicable_classifications=sensitive
        ),
        GovernancePolicy(
            policy_id="POL-003",
            name="Backup Governance",
            description="Restricted databases require backups.",
            severity=Severity.HIGH,
            required_backup=True,
            applicable_classifications=(
                DataClassification.RESTRICTED,
            )
        ),
        GovernancePolicy(
            policy_id="POL-004",
            name="Approved Cloud Regions",
            description="Restricted data must remain in approved regions.",
            severity=Severity.CRITICAL,
            allowed_regions=("ap-south-1", "ap-south-2"),
            applicable_classifications=(
                DataClassification.RESTRICTED,
            )
        )
    ]


def main() -> None:

    audit = AuditLogger()
    engine = PolicyEngine(build_policies())

    service = GovernanceService(engine, audit)

    residency = DataResidencyPolicy(
        "ORGANIZATION_DATA_RESIDENCY",
        {"ap-south-1", "ap-south-2"}
    )

    resources = [
        CloudResource(
            resource_id="RES-001",
            name="Customer Database",
            resource_type=ResourceType.DATABASE,
            provider="AWS",
            region="ap-south-1",
            data_classification=DataClassification.RESTRICTED,
            owner="data-platform-team",
            encrypted=False,
            public_access=True,
            backup_enabled=False
        ),
        CloudResource(
            resource_id="RES-002",
            name="Internal Application Server",
            resource_type=ResourceType.COMPUTE,
            provider="AWS",
            region="ap-south-1",
            data_classification=DataClassification.INTERNAL,
            owner="engineering-team",
            encrypted=True,
            public_access=False,
            backup_enabled=True
        ),
        CloudResource(
            resource_id="RES-003",
            name="Analytics Storage",
            resource_type=ResourceType.STORAGE,
            provider="Azure",
            region="centralindia",
            data_classification=DataClassification.RESTRICTED,
            owner="analytics-team",
            encrypted=True,
            public_access=False,
            backup_enabled=True
        )
    ]

    for resource in resources:
        service.register_resource(resource, "governance-admin")

    print("\nCLOUD GOVERNANCE ASSESSMENT")
    print("=" * 65)

    for resource in resources:

        print(f"\nResource: {resource.name}")

        residency_status = residency.evaluate(resource)

        print(
            f"Data residency: "
            f"{'COMPLIANT' if residency_status else 'NON_COMPLIANT'}"
        )

        results = service.evaluate_resource(
            resource.resource_id,
            "compliance-engine"
        )

        for result in results:

            print(
                f"{result.policy_id}: {result.status.value}"
            )

            for violation in result.violations:
                print(f"  - {violation}")

    print("\nAPPLYING AUTHORIZED REMEDIATION")
    print("=" * 65)

    service.remediate(
        "RES-001",
        "security-operator",
        encrypt=True,
        disable_public_access=True,
        enable_backup=True
    )

    print("\nREASSESSMENT")
    print("=" * 65)

    service.evaluate_resource(
        "RES-001",
        "compliance-engine"
    )

    print("\nCOMPLIANCE REPORT")
    print("=" * 65)

    report = service.report()

    for key, value in report.items():
        print(f"{key}: {value}")

    print(
        "\nAudit chain integrity:",
        audit.verify_integrity()
    )

    # Assertions exercise important system guarantees.
    assert len(service.resources) == 3
    assert service.report()["non_compliant_count"] >= 1
    assert audit.verify_integrity()

    try:
        service.get_resource("UNKNOWN-RESOURCE")
    except ResourceNotFoundError as error:
        logger.warning("Expected lookup failure: %s", error)

    print("\nAll governance checks completed.")

    service.export_report("cloud_compliance_report.json")

    print("Report exported to cloud_compliance_report.json")


if __name__ == "__main__":
    main()
