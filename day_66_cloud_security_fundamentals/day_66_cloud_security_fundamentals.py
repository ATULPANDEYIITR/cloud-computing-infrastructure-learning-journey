"""
Cloud Security Fundamentals
Shared Responsibility, Attack Surface, Cloud Threats, and Security Principles.

A self-contained cloud security posture assessment engine.

Features:
- Cloud shared responsibility model
- Cloud asset inventory
- Attack surface discovery
- IAM and least-privilege assessment
- Public exposure detection
- Encryption and logging validation
- Threat identification
- Risk scoring and prioritization
- Security recommendations
- JSON report generation
- Unit-style assertions
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any


class CloudProvider(Enum):
    AWS = "AWS"
    AZURE = "Azure"
    GCP = "GCP"


class AssetType(Enum):
    COMPUTE = "compute"
    STORAGE = "storage"
    DATABASE = "database"
    NETWORK = "network"
    IDENTITY = "identity"
    SERVERLESS = "serverless"


class Severity(Enum):
    CRITICAL = 4
    HIGH = 3
    MEDIUM = 2
    LOW = 1


class Responsibility(Enum):
    PROVIDER = "cloud_provider"
    CUSTOMER = "customer"
    SHARED = "shared"


@dataclass
class CloudAsset:
    asset_id: str
    name: str
    provider: CloudProvider
    asset_type: AssetType
    region: str
    internet_exposed: bool = False
    encryption_enabled: bool = True
    logging_enabled: bool = True
    mfa_enabled: bool = True
    least_privilege: bool = True
    network_restricted: bool = True
    patch_compliant: bool = True
    backup_enabled: bool = True
    sensitive_data: bool = False
    active: bool = True
    permissions: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not self.asset_id.strip():
            raise ValueError("Asset ID cannot be empty.")

        if not self.name.strip():
            raise ValueError("Asset name cannot be empty.")

        if not self.region.strip():
            raise ValueError("Cloud region cannot be empty.")

        if not isinstance(self.permissions, list):
            raise ValueError("Permissions must be a list.")

        if any(not isinstance(p, str) or not p.strip()
               for p in self.permissions):
            raise ValueError("Permissions must contain valid strings.")


@dataclass
class SecurityFinding:
    asset_id: str
    rule_id: str
    title: str
    severity: Severity
    description: str
    remediation: str
    responsibility: Responsibility
    risk_score: int


class SharedResponsibilityModel:
    """
    Responsibility varies by service model.

    IaaS: Customer manages guest OS, applications, data and IAM.
    PaaS: Provider manages platform infrastructure.
    SaaS: Provider manages application infrastructure.

    Customers retain responsibility for data, identities,
    access configuration and appropriate usage.
    """

    RESPONSIBILITIES = {
        "physical_datacenter": Responsibility.PROVIDER,
        "physical_network": Responsibility.PROVIDER,
        "hypervisor": Responsibility.PROVIDER,
        "guest_operating_system": Responsibility.CUSTOMER,
        "application": Responsibility.CUSTOMER,
        "data": Responsibility.CUSTOMER,
        "identity_access": Responsibility.CUSTOMER,
        "network_configuration": Responsibility.CUSTOMER,
        "encryption_configuration": Responsibility.CUSTOMER,
        "managed_platform": Responsibility.SHARED,
        "security_monitoring": Responsibility.SHARED,
        "incident_response": Responsibility.SHARED,
    }

    @classmethod
    def get_responsibility(cls, control: str) -> Responsibility:
        try:
            return cls.RESPONSIBILITIES[control]
        except KeyError:
            raise ValueError(f"Unknown security control: {control}")


class CloudSecurityScanner:

    RULES = {
        "PUBLIC_STORAGE": (Severity.CRITICAL, 40),
        "UNENCRYPTED_SENSITIVE_DATA": (Severity.CRITICAL, 35),
        "EXCESSIVE_PERMISSIONS": (Severity.HIGH, 25),
        "MFA_DISABLED": (Severity.HIGH, 25),
        "LOGGING_DISABLED": (Severity.HIGH, 20),
        "UNRESTRICTED_NETWORK": (Severity.HIGH, 20),
        "PATCH_NONCOMPLIANT": (Severity.MEDIUM, 15),
        "BACKUP_DISABLED": (Severity.MEDIUM, 15),
    }

    def __init__(self, assets: list[CloudAsset]):
        self.assets = assets
        self.findings: list[SecurityFinding] = []

    def scan(self) -> list[SecurityFinding]:
        self.findings.clear()
        seen_ids = set()

        for asset in self.assets:
            asset.validate()

            if asset.asset_id in seen_ids:
                raise ValueError(f"Duplicate asset ID: {asset.asset_id}")

            seen_ids.add(asset.asset_id)

            if not asset.active:
                continue

            if asset.asset_type == AssetType.STORAGE:
                if asset.internet_exposed:
                    self._add(
                        asset, "PUBLIC_STORAGE",
                        "Publicly accessible storage",
                        "Storage is accessible from the internet.",
                        "Disable public access and restrict access "
                        "through identity-based policies."
                    )

            if asset.sensitive_data and not asset.encryption_enabled:
                self._add(
                    asset, "UNENCRYPTED_SENSITIVE_DATA",
                    "Sensitive data is not encrypted",
                    "Sensitive information is stored without encryption.",
                    "Enable encryption at rest using managed or "
                    "customer-managed encryption keys."
                )

            if not asset.least_privilege or "*" in asset.permissions:
                self._add(
                    asset, "EXCESSIVE_PERMISSIONS",
                    "Excessive identity permissions",
                    "The asset has permissions exceeding operational needs.",
                    "Apply least privilege and remove wildcard permissions."
                )

            if not asset.mfa_enabled:
                self._add(
                    asset, "MFA_DISABLED",
                    "Multi-factor authentication is disabled",
                    "An identity or access control lacks MFA.",
                    "Enforce MFA for privileged and interactive accounts."
                )

            if not asset.logging_enabled:
                self._add(
                    asset, "LOGGING_DISABLED",
                    "Security logging is disabled",
                    "Security events may not be recorded.",
                    "Enable centralized, protected audit logging."
                )

            if not asset.network_restricted:
                self._add(
                    asset, "UNRESTRICTED_NETWORK",
                    "Network access is unrestricted",
                    "Network access is not adequately restricted.",
                    "Apply firewall rules, security groups and segmentation."
                )

            if not asset.patch_compliant:
                self._add(
                    asset, "PATCH_NONCOMPLIANT",
                    "Security patches are missing",
                    "The workload does not meet patch requirements.",
                    "Apply tested security updates and verify compliance."
                )

            if not asset.backup_enabled:
                self._add(
                    asset, "BACKUP_DISABLED",
                    "Backup protection is disabled",
                    "The asset does not have an enabled backup policy.",
                    "Configure encrypted backups and test restoration."
                )

        self.findings.sort(
            key=lambda finding: finding.risk_score,
            reverse=True
        )

        return self.findings

    def _add(
        self,
        asset: CloudAsset,
        rule_id: str,
        title: str,
        description: str,
        remediation: str
    ) -> None:
        severity, score = self.RULES[rule_id]

        self.findings.append(
            SecurityFinding(
                asset_id=asset.asset_id,
                rule_id=rule_id,
                title=title,
                severity=severity,
                description=description,
                remediation=remediation,
                responsibility=Responsibility.CUSTOMER,
                risk_score=score
            )
        )

    def summary(self) -> dict[str, Any]:
        counts = {severity.name: 0 for severity in Severity}

        for finding in self.findings:
            counts[finding.severity.name] += 1

        return {
            "total_assets": len(self.assets),
            "active_assets": sum(a.active for a in self.assets),
            "total_findings": len(self.findings),
            "severity_distribution": counts,
            "total_risk_score": sum(
                f.risk_score for f in self.findings
            ),
        }

    def export_json(self, filename: str) -> None:
        output = {
            "assessment": self.summary(),
            "findings": [
                {
                    **asdict(finding),
                    "severity": finding.severity.name,
                    "responsibility": finding.responsibility.value,
                }
                for finding in self.findings
            ]
        }

        path = Path(filename)
        path.write_text(
            json.dumps(output, indent=4),
            encoding="utf-8"
        )


def build_sample_environment() -> list[CloudAsset]:
    return [
        CloudAsset(
            asset_id="AWS-STORAGE-001",
            name="Customer Data Bucket",
            provider=CloudProvider.AWS,
            asset_type=AssetType.STORAGE,
            region="ap-south-1",
            internet_exposed=True,
            encryption_enabled=False,
            sensitive_data=True,
            logging_enabled=False,
            permissions=["*"],
        ),
        CloudAsset(
            asset_id="AZURE-VM-001",
            name="Application Server",
            provider=CloudProvider.AZURE,
            asset_type=AssetType.COMPUTE,
            region="centralindia",
            mfa_enabled=False,
            patch_compliant=False,
            network_restricted=False,
            permissions=["compute:read", "compute:write"],
        ),
        CloudAsset(
            asset_id="GCP-DB-001",
            name="Production Database",
            provider=CloudProvider.GCP,
            asset_type=AssetType.DATABASE,
            region="asia-south1",
            sensitive_data=True,
            encryption_enabled=True,
            logging_enabled=True,
            backup_enabled=False,
            permissions=["database:read"],
        ),
        CloudAsset(
            asset_id="AWS-IDENTITY-001",
            name="Application Service Identity",
            provider=CloudProvider.AWS,
            asset_type=AssetType.IDENTITY,
            region="ap-south-1",
            permissions=["storage:read"],
        ),
    ]


def run_tests() -> None:
    assert (
        SharedResponsibilityModel.get_responsibility("data")
        == Responsibility.CUSTOMER
    )

    assert (
        SharedResponsibilityModel.get_responsibility("hypervisor")
        == Responsibility.PROVIDER
    )

    scanner = CloudSecurityScanner(build_sample_environment())
    findings = scanner.scan()

    assert len(findings) > 0
    assert findings[0].risk_score >= findings[-1].risk_score

    # Inactive assets must not generate active security findings.
    inactive = CloudAsset(
        asset_id="TEST-001",
        name="Retired Storage",
        provider=CloudProvider.AWS,
        asset_type=AssetType.STORAGE,
        region="ap-south-1",
        internet_exposed=True,
        active=False,
    )

    assert CloudSecurityScanner([inactive]).scan() == []

    # Duplicate asset identifiers must be rejected.
    try:
        CloudSecurityScanner([inactive, inactive]).scan()
        raise AssertionError("Duplicate IDs were accepted.")
    except ValueError:
        pass

    print("All security assessment tests passed.")


def main() -> None:
    print("=" * 65)
    print("CLOUD SECURITY POSTURE ASSESSMENT")
    print("=" * 65)

    assets = build_sample_environment()
    scanner = CloudSecurityScanner(assets)

    findings = scanner.scan()

    print("\nSHARED RESPONSIBILITY")
    for control in [
        "physical_datacenter",
        "guest_operating_system",
        "data",
        "security_monitoring",
    ]:
        responsibility = (
            SharedResponsibilityModel.get_responsibility(control)
        )
        print(f"{control}: {responsibility.value}")

    print("\nSECURITY FINDINGS")
    for finding in findings:
        print(
            f"\n[{finding.severity.name}] {finding.title}"
            f"\nAsset: {finding.asset_id}"
            f"\nRisk score: {finding.risk_score}"
            f"\nDescription: {finding.description}"
            f"\nRemediation: {finding.remediation}"
        )

    print("\nASSESSMENT SUMMARY")
    print(json.dumps(scanner.summary(), indent=4))

    scanner.export_json("cloud_security_report.json")
    print("\nReport saved: cloud_security_report.json")

    run_tests()


if __name__ == "__main__":
    main()
