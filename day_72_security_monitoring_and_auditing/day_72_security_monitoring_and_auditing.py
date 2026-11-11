#!/usr/bin/env python3
"""
Security Monitoring and Auditing
Audit Logs | Access Logs | Security Alerts | Anomaly Detection

Python 3.10+
Standard-library implementation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import statistics
import tempfile
import uuid

from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
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

logger = logging.getLogger("security-monitor")


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EventType(str, Enum):
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILURE = "LOGIN_FAILURE"
    LOGOUT = "LOGOUT"
    ACCESS_GRANTED = "ACCESS_GRANTED"
    ACCESS_DENIED = "ACCESS_DENIED"
    PRIVILEGE_CHANGE = "PRIVILEGE_CHANGE"
    DATA_EXPORT = "DATA_EXPORT"
    CONFIGURATION_CHANGE = "CONFIGURATION_CHANGE"
    PASSWORD_CHANGE = "PASSWORD_CHANGE"
    FIREWALL_CHANGE = "FIREWALL_CHANGE"


class AlertStatus(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


# ============================================================
# DOMAIN MODELS
# ============================================================

@dataclass(frozen=True)
class SecurityEvent:
    event_id: str
    timestamp: datetime
    event_type: EventType
    user_id: str
    source_ip: str
    resource: str
    success: bool
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp.tzinfo is None:
            raise ValueError("Timestamp must include timezone information.")

        if not self.user_id.strip():
            raise ValueError("User ID cannot be empty.")

        if not self.source_ip.strip():
            raise ValueError("Source IP cannot be empty.")

        if len(self.resource) > 512:
            raise ValueError("Resource exceeds maximum length.")

        if len(self.details) > 30:
            raise ValueError("Too many event attributes.")

    @classmethod
    def create(
        cls,
        event_type: EventType,
        user_id: str,
        source_ip: str,
        resource: str,
        success: bool,
        details: Optional[dict[str, Any]] = None,
        timestamp: Optional[datetime] = None
    ) -> "SecurityEvent":

        return cls(
            event_id=str(uuid.uuid4()),
            timestamp=timestamp or datetime.now(timezone.utc),
            event_type=event_type,
            user_id=user_id,
            source_ip=source_ip,
            resource=resource,
            success=success,
            details=details or {}
        )


@dataclass
class SecurityAlert:
    alert_id: str
    timestamp: datetime
    severity: Severity
    category: str
    user_id: str
    description: str
    evidence: list[str]
    status: AlertStatus = AlertStatus.OPEN
    assigned_to: Optional[str] = None


@dataclass
class DetectionResult:
    event_id: str
    anomaly_score: float
    anomalies: list[str]
    severity: Severity


# ============================================================
# APPEND-ONLY AUDIT LOG
# ============================================================

class AuditLogger:
    """
    Maintains a SHA-256 hash chain.

    Each record contains the hash of the previous record.
    Modification, deletion, or reordering becomes detectable
    when the chain is verified.

    Production systems should periodically anchor chain heads
    in independent immutable storage.
    """

    def __init__(self):
        self.records: list[dict[str, Any]] = []
        self.last_hash = "0" * 64

    def append(self, event: SecurityEvent) -> dict[str, Any]:

        payload = {
            "event_id": event.event_id,
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type.value,
            "user_id": event.user_id,
            "source_ip": event.source_ip,
            "resource": event.resource,
            "success": event.success,
            "details": event.details
        }

        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":")
        )

        record_hash = hashlib.sha256(
            (self.last_hash + canonical).encode("utf-8")
        ).hexdigest()

        record = {
            "payload": payload,
            "previous_hash": self.last_hash,
            "record_hash": record_hash
        }

        self.records.append(record)
        self.last_hash = record_hash

        return record

    def verify(self) -> bool:

        previous_hash = "0" * 64

        for record in self.records:

            if record["previous_hash"] != previous_hash:
                return False

            canonical = json.dumps(
                record["payload"],
                sort_keys=True,
                separators=(",", ":")
            )

            expected = hashlib.sha256(
                (previous_hash + canonical).encode("utf-8")
            ).hexdigest()

            if expected != record["record_hash"]:
                return False

            previous_hash = expected

        return True

    def export_jsonl(self, destination: Path) -> None:

        destination.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with destination.open(
            "w",
            encoding="utf-8"
        ) as file:

            for record in self.records:
                file.write(json.dumps(record) + "\n")

    @staticmethod
    def load_jsonl(source: Path) -> list[dict[str, Any]]:

        records = []

        with source.open(encoding="utf-8") as file:

            for line_number, line in enumerate(file, 1):

                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON at line {line_number}"
                    ) from exc

        return records


# ============================================================
# ACCESS CONTROL MONITORING
# ============================================================

class AccessMonitor:

    SENSITIVE_RESOURCES = {
        "/admin",
        "/database",
        "/credentials",
        "/financial-records",
        "/security-configuration"
    }

    def __init__(self):
        self.user_roles = {
            "alice": {"developer"},
            "bob": {"administrator"},
            "carol": {"auditor"},
            "david": {"analyst"}
        }

        self.resource_permissions = {
            "/admin": {"administrator"},
            "/database": {"administrator", "developer"},
            "/credentials": {"administrator"},
            "/financial-records": {"administrator", "auditor"},
            "/reports": {"administrator", "auditor", "analyst"},
            "/application": {"administrator", "developer", "analyst"}
        }

    def authorize(
        self,
        user_id: str,
        resource: str
    ) -> bool:

        roles = self.user_roles.get(user_id, set())

        required_roles = self.resource_permissions.get(
            resource,
            set()
        )

        return bool(roles.intersection(required_roles))

    def change_role(
        self,
        user_id: str,
        new_role: str
    ) -> None:

        if user_id not in self.user_roles:
            raise ValueError("Unknown user.")

        if new_role not in {
            "administrator",
            "developer",
            "auditor",
            "analyst"
        }:
            raise ValueError("Invalid role.")

        self.user_roles[user_id] = {new_role}


# ============================================================
# ANOMALY DETECTION
# ============================================================

class AnomalyDetector:
    """
    Detects:
    1. Repeated failed authentication.
    2. Access from multiple IP addresses.
    3. Unauthorized sensitive-resource access.
    4. Privilege changes.
    5. Unusually large data exports.
    6. Unusual event frequency.

    The detector uses sliding time windows and transparent
    threshold-based rules.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        window_minutes: int = 10,
        export_threshold: int = 1000,
        event_threshold: int = 30
    ):

        if min(
            failure_threshold,
            window_minutes,
            export_threshold,
            event_threshold
        ) <= 0:
            raise ValueError("Detection thresholds must be positive.")

        self.failure_threshold = failure_threshold
        self.window = timedelta(minutes=window_minutes)
        self.export_threshold = export_threshold
        self.event_threshold = event_threshold

        self.events: deque[SecurityEvent] = deque()

    def analyze(
        self,
        event: SecurityEvent,
        access_monitor: AccessMonitor
    ) -> DetectionResult:

        self.events.append(event)

        cutoff = event.timestamp - self.window

        while (
            self.events
            and self.events[0].timestamp < cutoff
        ):
            self.events.popleft()

        user_events = [
            item
            for item in self.events
            if item.user_id == event.user_id
        ]

        anomalies = []
        score = 0.0

        failed_logins = sum(
            item.event_type == EventType.LOGIN_FAILURE
            for item in user_events
        )

        if failed_logins >= self.failure_threshold:
            anomalies.append("REPEATED_FAILED_AUTHENTICATION")
            score += 0.40

        unique_ips = {
            item.source_ip
            for item in user_events
            if item.event_type in {
                EventType.LOGIN_SUCCESS,
                EventType.LOGIN_FAILURE
            }
        }

        if len(unique_ips) >= 3:
            anomalies.append("MULTIPLE_SOURCE_IP_ADDRESSES")
            score += 0.25

        if event.event_type == EventType.ACCESS_DENIED:
            if event.resource in access_monitor.SENSITIVE_RESOURCES:
                anomalies.append("SENSITIVE_RESOURCE_ACCESS_DENIED")
                score += 0.30

        if event.event_type == EventType.PRIVILEGE_CHANGE:
            anomalies.append("PRIVILEGE_CHANGE")
            score += 0.50

        if event.event_type == EventType.DATA_EXPORT:

            exported = event.details.get("record_count", 0)

            if (
                isinstance(exported, bool)
                or not isinstance(exported, int)
                or exported < 0
            ):
                raise ValueError("Invalid data export record count.")

            if exported > self.export_threshold:
                anomalies.append("UNUSUAL_DATA_EXPORT")
                score += 0.45

        if len(user_events) > self.event_threshold:
            anomalies.append("HIGH_EVENT_FREQUENCY")
            score += 0.30

        score = min(score, 1.0)

        if score >= 0.75:
            severity = Severity.CRITICAL
        elif score >= 0.50:
            severity = Severity.HIGH
        elif score >= 0.25:
            severity = Severity.MEDIUM
        else:
            severity = Severity.LOW

        return DetectionResult(
            event_id=event.event_id,
            anomaly_score=round(score, 3),
            anomalies=anomalies,
            severity=severity
        )


# ============================================================
# SECURITY MONITORING ENGINE
# ============================================================

class SecurityMonitoringEngine:

    def __init__(self):

        self.audit = AuditLogger()
        self.access = AccessMonitor()
        self.detector = AnomalyDetector()

        self.alerts: list[SecurityAlert] = []
        self.processed_ids: set[str] = set()

        self.statistics = Counter()

    def process_event(
        self,
        event: SecurityEvent
    ) -> Optional[SecurityAlert]:

        if event.event_id in self.processed_ids:
            raise ValueError("Duplicate event identifier.")

        self.processed_ids.add(event.event_id)

        self.audit.append(event)

        self.statistics[event.event_type.value] += 1

        anomalies = self.detector.analyze(
            event,
            self.access
        )

        # Access authorization is evaluated separately from
        # anomaly detection.
        if event.event_type == EventType.ACCESS_GRANTED:

            if not self.access.authorize(
                event.user_id,
                event.resource
            ):
                raise PermissionError(
                    "Unauthorized access was recorded as granted."
                )

        if not anomalies.anomalies:
            return None

        alert = SecurityAlert(
            alert_id=str(uuid.uuid4()),
            timestamp=event.timestamp,
            severity=anomalies.severity,
            category=", ".join(anomalies.anomalies),
            user_id=event.user_id,
            description=(
                f"Security anomalies detected for {event.user_id}"
            ),
            evidence=[event.event_id]
        )

        self.alerts.append(alert)

        logger.warning(
            "Alert %s: %s",
            alert.severity.value,
            alert.category
        )

        return alert

    def update_alert(
        self,
        alert_id: str,
        status: AlertStatus,
        assigned_to: Optional[str] = None
    ) -> None:

        alert = next(
            (
                item for item in self.alerts
                if item.alert_id == alert_id
            ),
            None
        )

        if alert is None:
            raise ValueError("Alert not found.")

        if alert.status in {
            AlertStatus.RESOLVED,
            AlertStatus.FALSE_POSITIVE
        }:
            raise ValueError("Closed alerts cannot be modified.")

        if status == AlertStatus.INVESTIGATING and not assigned_to:
            raise ValueError(
                "Investigation requires an assigned analyst."
            )

        alert.status = status

        if assigned_to:
            alert.assigned_to = assigned_to

    def report(self) -> dict[str, Any]:

        severity_counts = Counter(
            alert.severity.value
            for alert in self.alerts
        )

        return {
            "total_events": len(self.audit.records),
            "total_alerts": len(self.alerts),
            "severity_distribution": dict(severity_counts),
            "event_distribution": dict(self.statistics),
            "audit_integrity": self.audit.verify(),
            "open_alerts": sum(
                alert.status == AlertStatus.OPEN
                for alert in self.alerts
            )
        }


# ============================================================
# STATISTICAL ANOMALY DETECTION
# ============================================================

def calculate_z_scores(
    values: list[float]
) -> list[float]:

    if len(values) < 2:
        return [0.0] * len(values)

    if any(not math.isfinite(value) for value in values):
        raise ValueError("Input values must be finite.")

    mean = statistics.mean(values)
    deviation = statistics.pstdev(values)

    if deviation == 0:
        return [0.0] * len(values)

    return [
        round((value - mean) / deviation, 3)
        for value in values
    ]


def detect_statistical_anomalies(
    values: list[float],
    threshold: float = 2.0
) -> list[int]:

    if threshold <= 0:
        raise ValueError("Threshold must be positive.")

    scores = calculate_z_scores(values)

    return [
        index
        for index, score in enumerate(scores)
        if abs(score) > threshold
    ]


# ============================================================
# SECURITY EVENT GENERATION
# ============================================================

def generate_sample_events() -> list[SecurityEvent]:

    base = datetime.now(timezone.utc)

    events = []

    events.append(
        SecurityEvent.create(
            EventType.LOGIN_SUCCESS,
            "alice",
            "192.168.1.10",
            "/authentication",
            True,
            timestamp=base
        )
    )

    events.append(
        SecurityEvent.create(
            EventType.ACCESS_GRANTED,
            "alice",
            "192.168.1.10",
            "/application",
            True,
            timestamp=base + timedelta(seconds=5)
        )
    )

    for index in range(6):

        events.append(
            SecurityEvent.create(
                EventType.LOGIN_FAILURE,
                "david",
                "203.0.113.50",
                "/authentication",
                False,
                details={"attempt": index + 1},
                timestamp=base + timedelta(minutes=1, seconds=index)
            )
        )

    events.append(
        SecurityEvent.create(
            EventType.ACCESS_DENIED,
            "alice",
            "192.168.1.10",
            "/credentials",
            False,
            timestamp=base + timedelta(minutes=2)
        )
    )

    events.append(
        SecurityEvent.create(
            EventType.PRIVILEGE_CHANGE,
            "bob",
            "192.168.1.20",
            "/admin",
            True,
            details={
                "target_user": "alice",
                "new_role": "administrator"
            },
            timestamp=base + timedelta(minutes=3)
        )
    )

    events.append(
        SecurityEvent.create(
            EventType.DATA_EXPORT,
            "david",
            "203.0.113.50",
            "/financial-records",
            True,
            details={"record_count": 5000},
            timestamp=base + timedelta(minutes=4)
        )
    )

    return events


# ============================================================
# TESTS
# ============================================================

def run_tests() -> None:

    engine = SecurityMonitoringEngine()

    events = generate_sample_events()

    for event in events:
        engine.process_event(event)

    assert len(engine.audit.records) == len(events)
    assert engine.audit.verify()
    assert len(engine.alerts) >= 3

    assert engine.access.authorize(
        "alice",
        "/application"
    )

    assert not engine.access.authorize(
        "alice",
        "/credentials"
    )

    assert calculate_z_scores([10, 10, 10]) == [0.0, 0.0, 0.0]

    assert detect_statistical_anomalies(
        [10, 11, 9, 10, 100],
        1.5
    ) == [4]

    try:
        engine.process_event(events[0])
        raise AssertionError("Duplicate event was accepted.")
    except ValueError:
        pass

    # Verify tamper detection on a separate audit chain.
    tamper_test = AuditLogger()
    tamper_test.append(events[0])
    tamper_test.records[0]["payload"]["user_id"] = "attacker"
    assert not tamper_test.verify()

    with tempfile.TemporaryDirectory() as directory:

        destination = Path(directory) / "audit.jsonl"

        engine.audit.export_jsonl(destination)

        restored = AuditLogger.load_jsonl(destination)

        assert len(restored) == len(events)

    print("All security monitoring tests passed.")


# ============================================================
# EXECUTION
# ============================================================

def main() -> None:

    engine = SecurityMonitoringEngine()

    for event in generate_sample_events():

        try:
            alert = engine.process_event(event)

            if alert:
                print(
                    f"[{alert.severity.value}] "
                    f"{alert.category} | "
                    f"User: {alert.user_id}"
                )

        except (ValueError, PermissionError) as exc:
            logger.error("Event processing failed: %s", exc)

    print("\nSECURITY MONITORING REPORT")

    print(
        json.dumps(
            engine.report(),
            indent=4
        )
    )

    print("\nSTATISTICAL DETECTION")

    observations = [12, 13, 11, 12, 14, 13, 90]

    print(
        "Anomalous observation indexes:",
        detect_statistical_anomalies(observations)
    )

    run_tests()


if __name__ == "__main__":
    main()
