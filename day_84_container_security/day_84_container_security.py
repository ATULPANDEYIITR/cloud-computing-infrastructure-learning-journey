#!/usr/bin/env python3
"""
Container Security Governance Simulator

Demonstrates:
- Container image vulnerability scanning
- CVE severity and policy evaluation
- Minimal image enforcement
- Non-root execution
- Runtime security events
- Secret detection and management
- Image provenance and digest verification
- Deployment admission decisions
- Security reporting

Requires Python 3.10 or later.
Uses only the Python standard library.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(Enum):
    CRITICAL = 5
    HIGH = 4
    MEDIUM = 3
    LOW = 2
    UNKNOWN = 1


class ImageStatus(Enum):
    DRAFT = "draft"
    SCANNED = "scanned"
    APPROVED = "approved"
    BLOCKED = "blocked"


class RuntimeEventType(Enum):
    SHELL_EXECUTION = "shell_execution"
    PRIVILEGED_PROCESS = "privileged_process"
    FILESYSTEM_WRITE = "filesystem_write"
    NETWORK_CONNECTION = "network_connection"
    SECRET_ACCESS = "secret_access"
    PROCESS_EXECUTION = "process_execution"


class Decision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW = "review"


@dataclass(frozen=True)
class Vulnerability:
    cve_id: str
    package: str
    installed_version: str
    fixed_version: str | None
    severity: Severity
    exploitable: bool = False

    def __post_init__(self):
        if not re.fullmatch(r"CVE-\d{4}-\d{4,}", self.cve_id):
            raise ValueError(f"Invalid CVE identifier: {self.cve_id}")
        if not self.package.strip():
            raise ValueError("Package name cannot be empty")
        if not self.installed_version.strip():
            raise ValueError("Installed version cannot be empty")


@dataclass
class ContainerImage:
    name: str
    tag: str
    base_image: str
    digest: str
    packages: list[str]
    vulnerabilities: list[Vulnerability]
    user_id: int
    size_mb: float
    privileged: bool = False
    contains_shell: bool = False
    secrets_detected: list[str] = field(default_factory=list)
    signature_verified: bool = False
    status: ImageStatus = ImageStatus.DRAFT

    def __post_init__(self):
        if not self.name.strip() or not self.tag.strip():
            raise ValueError("Image name and tag are required")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", self.digest):
            raise ValueError("Image digest must be a SHA-256 digest")
        if self.size_mb <= 0:
            raise ValueError("Image size must be positive")
        if self.user_id < 0:
            raise ValueError("User ID cannot be negative")


@dataclass(frozen=True)
class SecurityPolicy:
    maximum_critical: int = 0
    maximum_high: int = 0
    maximum_medium: int = 5
    maximum_image_size_mb: float = 200
    require_non_root: bool = True
    forbid_privileged: bool = True
    forbid_shell: bool = False
    require_signature: bool = True
    require_vulnerability_fixes: bool = False
    block_unknown_severity: bool = True
    require_no_secrets: bool = True


@dataclass
class SecurityFinding:
    control: str
    severity: Severity
    description: str
    remediation: str


@dataclass
class ScanReport:
    image_name: str
    digest: str
    scanned_at: str
    findings: list[SecurityFinding]
    vulnerability_counts: dict[str, int]
    decision: Decision

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_name": self.image_name,
            "digest": self.digest,
            "scanned_at": self.scanned_at,
            "findings": [
                {
                    "control": f.control,
                    "severity": f.severity.name,
                    "description": f.description,
                    "remediation": f.remediation,
                }
                for f in self.findings
            ],
            "vulnerability_counts": self.vulnerability_counts,
            "decision": self.decision.value,
        }


class ContainerSecurityError(Exception):
    pass


class ImageScanner:
    def __init__(self, policy: SecurityPolicy):
        self.policy = policy

    def scan(self, image: ContainerImage) -> ScanReport:
        findings: list[SecurityFinding] = []
        counts = {severity.name: 0 for severity in Severity}

        for vulnerability in image.vulnerabilities:
            counts[vulnerability.severity.name] += 1

            findings.append(
                SecurityFinding(
                    control="CVE_SCAN",
                    severity=vulnerability.severity,
                    description=(
                        f"{vulnerability.cve_id}: "
                        f"{vulnerability.package} "
                        f"{vulnerability.installed_version}"
                    ),
                    remediation=(
                        f"Upgrade to {vulnerability.fixed_version}"
                        if vulnerability.fixed_version
                        else "Investigate mitigation or package replacement"
                    ),
                )
            )

            if (
                self.policy.require_vulnerability_fixes
                and vulnerability.fixed_version is None
            ):
                findings.append(
                    SecurityFinding(
                        "UNFIXED_VULNERABILITY",
                        vulnerability.severity,
                        f"No known fix for {vulnerability.cve_id}",
                        "Apply compensating controls or replace the package",
                    )
                )

        def add_finding(
            control: str,
            severity: Severity,
            description: str,
            remediation: str,
        ) -> None:
            findings.append(
                SecurityFinding(control, severity, description, remediation)
            )

        if self.policy.require_non_root and image.user_id == 0:
            add_finding(
                "NON_ROOT_EXECUTION",
                Severity.HIGH,
                "Image executes as root",
                "Configure a dedicated non-root USER",
            )

        if self.policy.forbid_privileged and image.privileged:
            add_finding(
                "PRIVILEGED_CONTAINER",
                Severity.CRITICAL,
                "Image requests privileged execution",
                "Remove privileged execution and restrict Linux capabilities",
            )

        if self.policy.forbid_shell and image.contains_shell:
            add_finding(
                "MINIMAL_IMAGE",
                Severity.MEDIUM,
                "Image contains a shell",
                "Use a minimal runtime image without unnecessary utilities",
            )

        if image.size_mb > self.policy.maximum_image_size_mb:
            add_finding(
                "IMAGE_SIZE",
                Severity.MEDIUM,
                f"Image size {image.size_mb} MB exceeds policy",
                "Remove build tools, unused packages and unnecessary files",
            )

        if self.policy.require_signature and not image.signature_verified:
            add_finding(
                "IMAGE_SIGNATURE",
                Severity.HIGH,
                "Image signature is not verified",
                "Verify provenance and image signatures before deployment",
            )

        if self.policy.require_no_secrets and image.secrets_detected:
            add_finding(
                "SECRET_EXPOSURE",
                Severity.CRITICAL,
                "Potential secrets detected in image",
                "Remove secrets, rotate exposed credentials and rebuild image",
            )

        for vulnerability in image.vulnerabilities:
            if (
                vulnerability.severity == Severity.UNKNOWN
                and self.policy.block_unknown_severity
            ):
                add_finding(
                    "UNKNOWN_SEVERITY",
                    Severity.HIGH,
                    f"Unknown severity: {vulnerability.cve_id}",
                    "Investigate and classify the vulnerability",
                )

        thresholds = {
            Severity.CRITICAL: self.policy.maximum_critical,
            Severity.HIGH: self.policy.maximum_high,
            Severity.MEDIUM: self.policy.maximum_medium,
        }

        for severity, maximum in thresholds.items():
            if counts[severity.name] > maximum:
                add_finding(
                    "VULNERABILITY_THRESHOLD",
                    severity,
                    f"{counts[severity.name]} {severity.name} vulnerabilities; "
                    f"maximum permitted is {maximum}",
                    "Patch, remove or mitigate affected packages",
                )

        if any(
            finding.control in {
                "PRIVILEGED_CONTAINER",
                "SECRET_EXPOSURE",
                "VULNERABILITY_THRESHOLD",
                "IMAGE_SIGNATURE",
                "NON_ROOT_EXECUTION",
                "UNKNOWN_SEVERITY",
                "UNFIXED_VULNERABILITY",
            }
            and finding.severity.value >= Severity.HIGH.value
            for finding in findings
        ):
            decision = Decision.DENY
            image.status = ImageStatus.BLOCKED
        elif findings:
            decision = Decision.REVIEW
            image.status = ImageStatus.SCANNED
        else:
            decision = Decision.ALLOW
            image.status = ImageStatus.APPROVED

        return ScanReport(
            image_name=image.name,
            digest=image.digest,
            scanned_at=datetime.now(timezone.utc).isoformat(),
            findings=findings,
            vulnerability_counts=counts,
            decision=decision,
        )


@dataclass
class RuntimeEvent:
    container_id: str
    event_type: RuntimeEventType
    process: str
    user_id: int
    timestamp: str
    details: str = ""


class RuntimeMonitor:
    """Evaluates runtime behavior against a defensive allow policy."""

    def __init__(self):
        self.blocked_processes = {"nc", "ncat", "socat", "tcpdump"}
        self.events: list[RuntimeEvent] = []

    def evaluate(self, event: RuntimeEvent) -> Decision:
        self.events.append(event)

        process = Path(event.process).name.lower()

        if event.user_id == 0:
            return Decision.DENY

        if event.event_type == RuntimeEventType.PRIVILEGED_PROCESS:
            return Decision.DENY

        if event.event_type == RuntimeEventType.SHELL_EXECUTION:
            return Decision.DENY

        if process in self.blocked_processes:
            return Decision.DENY

        if event.event_type == RuntimeEventType.SECRET_ACCESS:
            return Decision.REVIEW

        if event.event_type == RuntimeEventType.FILESYSTEM_WRITE:
            return Decision.REVIEW

        return Decision.ALLOW

    def report(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in self.events:
            key = event.event_type.value
            counts[key] = counts.get(key, 0) + 1
        return counts


class SecretScanner:
    """Detects common accidental credential patterns."""

    PATTERNS = {
        "AWS_ACCESS_KEY": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "PRIVATE_KEY": re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
        "GITHUB_TOKEN": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
        "GENERIC_PASSWORD": re.compile(
            r"(?i)(?:password|passwd|secret)\s*[:=]\s*['\"]?[^'\"\s]{8,}"
        ),
    }

    def scan_text(self, content: str) -> list[str]:
        return [
            name
            for name, pattern in self.PATTERNS.items()
            if pattern.search(content)
        ]


class DeploymentGate:
    def __init__(self, scanner: ImageScanner):
        self.scanner = scanner
        self.audit_log: list[dict[str, Any]] = []

    def deploy(self, image: ContainerImage) -> Decision:
        report = self.scanner.scan(image)

        record = report.to_dict()
        self.audit_log.append(record)

        if report.decision != Decision.ALLOW:
            raise ContainerSecurityError(
                f"Deployment denied: {image.name}; "
                f"decision={report.decision.value}"
            )

        return Decision.ALLOW

    def export_audit(self, destination: str) -> None:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write atomically to avoid leaving a partially written audit file.
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self.audit_log, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)


def build_demo_image() -> ContainerImage:
    return ContainerImage(
        name="payments-api",
        tag="1.4.2",
        base_image="distroless/python3-debian12",
        digest="sha256:" + "a" * 64,
        packages=["python3", "application-runtime"],
        vulnerabilities=[
            Vulnerability(
                "CVE-2024-12345",
                "example-library",
                "1.0.0",
                "1.0.2",
                Severity.LOW,
            ),
        ],
        user_id=10001,
        size_mb=48,
        privileged=False,
        contains_shell=False,
        secrets_detected=[],
        signature_verified=True,
    )


def demonstrate_security() -> None:
    policy = SecurityPolicy(
        maximum_critical=0,
        maximum_high=0,
        maximum_medium=3,
        maximum_image_size_mb=100,
        require_non_root=True,
        forbid_privileged=True,
        forbid_shell=True,
        require_signature=True,
    )

    scanner = ImageScanner(policy)
    gate = DeploymentGate(scanner)

    image = build_demo_image()
    report = scanner.scan(image)

    print("\nIMAGE SCAN")
    print(json.dumps(report.to_dict(), indent=2))

    # A second scan is used for the actual deployment decision.
    print("\nDEPLOYMENT")
    try:
        print(gate.deploy(image).value)
    except ContainerSecurityError as error:
        print(error)

    compromised_image = build_demo_image()
    compromised_image.name = "compromised-api"
    compromised_image.user_id = 0
    compromised_image.secrets_detected = ["PRIVATE_KEY"]
    compromised_image.signature_verified = False

    print("\nNEGATIVE TEST")
    try:
        gate.deploy(compromised_image)
    except ContainerSecurityError as error:
        print(error)

    monitor = RuntimeMonitor()

    events = [
        RuntimeEvent(
            "container-001",
            RuntimeEventType.PROCESS_EXECUTION,
            "python",
            10001,
            datetime.now(timezone.utc).isoformat(),
        ),
        RuntimeEvent(
            "container-001",
            RuntimeEventType.SHELL_EXECUTION,
            "/bin/sh",
            10001,
            datetime.now(timezone.utc).isoformat(),
        ),
        RuntimeEvent(
            "container-001",
            RuntimeEventType.SECRET_ACCESS,
            "application",
            10001,
            datetime.now(timezone.utc).isoformat(),
            "Unexpected access to credential mount",
        ),
    ]

    print("\nRUNTIME SECURITY")
    for event in events:
        print(event.event_type.value, monitor.evaluate(event).value)

    print("Event counts:", monitor.report())

    secret_scanner = SecretScanner()
    findings = secret_scanner.scan_text(
        "password=ExampleSecret123456"
    )
    print("\nSECRET SCAN:", findings)

    print("\nASSERTIONS")
    assert report.decision == Decision.ALLOW
    assert monitor.evaluate(
        RuntimeEvent(
            "container-002",
            RuntimeEventType.SHELL_EXECUTION,
            "sh",
            10001,
            datetime.now(timezone.utc).isoformat(),
        )
    ) == Decision.DENY
    assert findings == ["GENERIC_PASSWORD"]
    assert scanner.scan(compromised_image).decision == Decision.DENY

    print("All security tests passed.")


if __name__ == "__main__":
    try:
        demonstrate_security()
    except (ValueError, OSError, ContainerSecurityError) as error:
        print(f"Execution error: {error}", file=sys.stderr)
        sys.exit(1)
