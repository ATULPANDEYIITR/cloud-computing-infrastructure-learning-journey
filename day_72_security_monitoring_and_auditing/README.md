# Security Monitoring and Auditing

## 1. Domain Architecture

Security monitoring and auditing provide mechanisms for recording system activity, identifying suspicious behavior, evaluating access decisions, and maintaining evidence for security investigations.

The implementation separates four related but distinct areas:

| Area | Primary responsibility | Main information |
|---|---|---|
| Audit logs | Preserve evidence of important system events | Actor, action, resource, timestamp, outcome |
| Access logs | Record authorization and resource-access decisions | Requested permission, resource, decision, source |
| Security alerts | Identify and communicate potential security incidents | Severity, category, evidence, investigation status |
| Anomaly detection | Identify activity that deviates from expected behavior | Thresholds, event frequency, statistical deviations |

These components operate together but serve different purposes.

An audit record documents an event. An access record explains whether a resource-access request was allowed or denied. An anomaly detector evaluates observed behavior. An alert communicates a condition requiring investigation.

### Architecture

Organization
  |
  +-- Monitored Systems
  |     |
  |     +-- Application
  |     +-- Identity Management
  |     +-- Financial Systems
  |
  +-- Security Users
  |     |
  |     +-- Roles
  |     +-- Permissions
  |
  +-- Event Collection
        |
        +-- Audit Logging
        |
        +-- Access Monitoring
        |
        +-- Anomaly Detection
        |
        +-- Security Alert Generation
        |
        +-- Investigation
        |
        +-- Reporting

## 2. Audit Logs

An audit log is a chronological record of security-relevant operations performed within an information system.

Typical events include:

- Successful authentication.
- Failed authentication.
- Logout.
- Permission changes.
- Privilege escalation.
- Configuration changes.
- Password changes.
- Firewall modifications.
- Sensitive data exports.
- Administrative operations.

### 2.1 Audit event structure

Each security event contains:

| Attribute | Purpose |
|---|---|
| Event ID | Unique event identification |
| Timestamp | Time at which the event occurred |
| Event type | Classification of the operation |
| User ID | Identity associated with the operation |
| Source IP | Originating network address |
| Resource | Affected system resource |
| Success | Operation outcome |
| Details | Structured supplementary information |

The implementations use structured event objects rather than unstructured log messages.

Timestamps include timezone information. This is important when events originate from multiple systems operating in different geographical regions.

### 2.2 Append-only logging

Audit evidence should not be silently modified or deleted.

The Python, JavaScript, C++17, and Java 17 implementations demonstrate hash-chained audit records.

Each record contains:

- The event information.
- The previous record's hash.
- The current record's hash.

The calculation is:

`Current Hash = SHA-256(Previous Hash + Canonical Event)`

The first record uses a fixed initial hash.

The resulting structure is:

Event 1 --> Hash 1
              |
Event 2 --> Hash 2
              |
Event 3 --> Hash 3
              |
Event 4 --> Hash 4

Changing an earlier event causes subsequent chain verification to fail.

Canonical serialization is important because equivalent structured data must produce consistent hash inputs.

**Security limitation:** A hash chain alone does not establish trustworthy storage. An attacker with unrestricted write access to the entire log and its hash state may reconstruct the chain. Production implementations should combine append-only storage, restricted administrative privileges, independent integrity checkpoints, digital signatures where appropriate, and off-system retention.

### 2.3 Audit event processing

The event-processing sequence is:

1. Validate the incoming event.
2. Verify its identifier has not already been processed.
3. Validate relevant access decisions.
4. Append the event to the audit log.
5. Update event statistics.
6. Evaluate detection rules.
7. Generate an alert when suspicious conditions are detected.
8. Preserve evidence for investigation.

This sequence separates evidence collection from subsequent interpretation.

An event does not need to produce an alert to remain an important audit record.

## 3. Access Logs and Authorization

Access logging records attempts to interact with protected resources.

An access decision is generally based on:

- User identity.
- Assigned roles.
- Requested resource.
- Requested operation.
- Current account status.
- Applicable permissions.

### 3.1 Role-Based Access Control

The implementations use Role-Based Access Control (RBAC).

RBAC associates users with roles and roles with permissions.

The example environment defines four roles:

| Role | Access characteristics |
|---|---|
| Administrator | Administrative and sensitive-resource access |
| Developer | Application and database development access |
| Auditor | Read-only compliance and financial-record access |
| Analyst | Operational application and reporting access |

A simplified permission relationship is:

User --> Role --> Permission --> Resource

For example:

- Alice is a developer.
- Developers can access the application.
- Developers can read the database.
- Developers cannot access administrative credentials.

The authorization function checks whether at least one assigned role grants the requested permission.

An unknown user, unknown resource, inactive account, or missing permission results in denial.

### 3.2 Access decisions

Two outcomes are represented:

| Decision | Meaning |
|---|---|
| ALLOW | The requested operation satisfies the authorization policy |
| DENY | The requested operation does not satisfy the authorization policy |

An access decision and an audit event are separate records.

The access record references the corresponding audit record. This provides a relationship between the authorization outcome and its original event.

A successful access event must not contradict the authorization policy.

The SQL implementation enforces this relationship through an access-log validation trigger.

### 3.3 Least privilege

The least-privilege principle restricts each account to the permissions necessary for its responsibilities.

The sample permission model prevents ordinary developers and analysts from accessing credentials or unrestricted administrative resources.

Privilege modifications should be separately audited because changing an account's role can change the security boundary of an entire application.

## 4. Security Alerts

A security alert represents a condition requiring attention from a security operator or analyst.

An alert is not automatically proof of a security incident. It represents a detection result that requires appropriate interpretation.

### 4.1 Alert attributes

| Attribute | Description |
|---|---|
| Alert ID | Unique alert identifier |
| Timestamp | Alert creation time |
| User ID | Associated identity |
| Severity | Operational priority |
| Category | Detection rule or anomaly |
| Score | Numerical risk indicator |
| Evidence | Related audit event identifiers |
| Status | Current investigation state |
| Assigned analyst | Responsible investigator |

### 4.2 Severity classification

The implementations use a normalized score between zero and one.

| Score | Severity |
|---|---|
| 0.00–0.24 | LOW |
| 0.25–0.49 | MEDIUM |
| 0.50–0.74 | HIGH |
| 0.75–1.00 | CRITICAL |

The score combines selected detection-rule contributions.

A higher severity indicates a greater operational priority under the configured rules. It is not a calibrated probability that an attack has occurred.

### 4.3 Alert lifecycle

OPEN
  |
  v
INVESTIGATING
  |
  +------> RESOLVED
  |
  +------> FALSE_POSITIVE

An alert can also remain OPEN until an analyst begins investigating it.

The implemented rules require an analyst assignment before an alert can enter the INVESTIGATING state.

Resolved and false-positive alerts are terminal states in the example implementations.

The SQL implementation enforces these state restrictions through a trigger.

### 4.4 Evidence preservation

An alert should reference the events that caused it to be generated.

The PostgreSQL implementation uses the `alert_evidence` table to associate alerts with audit records.

This relationship supports:

- Investigation timelines.
- Correlation between multiple events.
- Reproducibility of detection decisions.
- Incident reporting.
- Historical review.

Evidence should be retained according to the applicable organizational retention and privacy policies.

## 5. Anomaly Detection

Anomaly detection identifies activity that differs from an expected behavioral pattern.

The project implements two complementary approaches:

1. Rule-based detection.
2. Statistical anomaly detection.

### 5.1 Rule-based detection

Rule-based detection evaluates explicit conditions.

The following rules are implemented:

| Detection rule | Trigger condition | Contribution |
|---|---|---:|
| Repeated authentication failures | Five or more failures in ten minutes | 0.40 |
| Multiple source addresses | Three or more authentication source IPs | 0.25 |
| Sensitive-resource denial | Denied access to a sensitive resource | 0.30 |
| Privilege modification | A privilege-change event | 0.50 |
| Large data export | More than 1,000 exported records | 0.45 |
| High event frequency | More than 30 events in the window | 0.30 |

The combined score is capped at 1.0.

For example, repeated authentication failures combined with a sensitive-resource access denial produce:

`0.40 + 0.30 = 0.70`

The corresponding severity is HIGH.

A privilege modification combined with repeated authentication failures produces:

`0.50 + 0.40 = 0.90`

The corresponding severity is CRITICAL.

These values are illustrative rule weights. A production security program should calibrate thresholds using historical incident data, false-positive analysis, and operational requirements.

### 5.2 Sliding-window detection

A sliding time window evaluates recent activity rather than the entire historical event collection.

For a ten-minute window:

- New events enter the window.
- Expired events are removed.
- Events are grouped by user.
- Detection conditions are evaluated against recent activity.

The Python implementation uses `deque`.

The JavaScript implementation uses an event array and user-event counters.

The C++17 implementation uses `std::deque`.

The Java implementation uses `ArrayDeque`.

The sliding-window approach avoids repeatedly processing an unlimited historical event collection.

A production implementation should also handle out-of-order events, event-time watermarks, late-arriving records, and clock synchronization.

### 5.3 Statistical anomaly detection

Statistical detection uses numerical observations such as:

- Requests per minute.
- Authentication failures per hour.
- Data transferred per session.
- Number of distinct source addresses.
- Database operations per user.
- Resource consumption.

The project implements the Z-score method.

The formula is:

\[
z = \frac{x-\mu}{\sigma}
\]

Where:

- \(x\) represents an observation.
- \(\mu\) represents the sample population mean.
- \(\sigma\) represents the population standard deviation.

An observation is flagged when:

\[
|z| > T
\]

Here, \(T\) is a configurable threshold.

The examples use population standard deviation.

If all observations are identical, the standard deviation is zero. The implementations return no statistical anomalies instead of dividing by zero.

Z-scores are useful for detecting unusually high or low numerical observations, but they are sensitive to distribution shape and extreme values. They should not be interpreted as a complete security detection system.

## 6. Python Implementation

The Python implementation provides a complete repository-independent security event simulator.

### Implemented components

| Component | Responsibility |
|---|---|
| `SecurityEvent` | Immutable event representation |
| `SecurityAlert` | Alert state and evidence |
| `AuditLogger` | Hash-chained audit records |
| `AccessMonitor` | RBAC evaluation |
| `AnomalyDetector` | Sliding-window detection |
| `SecurityMonitoringEngine` | Event orchestration |
| `DetectionResult` | Detection output |

### Important implementation decisions

- Dataclasses represent structured security events.
- Enums prevent inconsistent event and status values.
- Dictionaries maintain role and permission mappings.
- Sets enforce uniqueness and support efficient membership checks.
- Deques maintain the sliding time window.
- Exceptions reject malformed and duplicate events.
- JSON Lines provides a practical structured export format.
- Temporary directories isolate file-export tests.

The `AuditLogger` verifies the complete hash chain.

The `SecurityMonitoringEngine` separates event ingestion, authorization, detection, and alert reporting.

The test suite validates duplicate detection, access decisions, audit integrity, alert creation, statistical detection, and file serialization.

### Execution

Python 3.10 or later is required.

Run the file using:

`python security_monitoring.py`

No third-party package installation is required.

## 7. JavaScript Implementation

The JavaScript implementation uses Node.js event-driven architecture.

It provides a complementary design focused on asynchronous event ingestion and service-oriented monitoring.

### Implemented components

| Component | Responsibility |
|---|---|
| `AuditLog` | Append-only audit records |
| `AccessPolicy` | Role-based authorization |
| `AnomalyDetector` | Time-window analysis |
| `AlertManager` | Alert creation and lifecycle |
| `SecurityMonitor` | Event orchestration |
| `EventEmitter` | Audit and alert notifications |

### Event-driven processing

The monitoring service emits two important events:

- `audit`: emitted when an event is recorded.
- `security-alert`: emitted when an anomaly is detected.

Other application components can subscribe to these events.

This separates monitoring from downstream operations such as incident dashboards, notifications, and security case management.

### Asynchronous processing

The ingestion method serializes event processing through a Promise chain.

This preserves deterministic ordering within the process and avoids concurrent modifications of the audit chain.

It does not provide distributed ordering or crash-safe delivery.

Production systems should use durable message queues, idempotent consumers, transactional persistence, and controlled retry policies.

### Execution

Node.js 18 or later is required.

Run:

`node security_monitoring.js`

The application writes a JSON Lines audit export named `security-audit.jsonl` in the current directory when that destination does not already exist.

No third-party npm packages are required.

## 8. C++17 Implementation

The C++17 implementation focuses on a compact security governance and event-processing engine.

### Implemented components

| Component | Responsibility |
|---|---|
| `SecurityEvent` | Event domain model |
| `AccessPolicy` | Permission evaluation |
| `SHA256` | SHA-256 hash calculation |
| `AuditLog` | Integrity-linked event storage |
| `AnomalyDetector` | Sliding-window detection |
| `SecurityAlert` | Security incident representation |
| `SecurityMonitoringEngine` | Central processing service |

### Data structures

The implementation uses:

- `std::unordered_map` for user-role lookup.
- `std::unordered_set` for event uniqueness.
- `std::map` for deterministic reporting.
- `std::set` for role and permission membership.
- `std::deque` for sliding-window processing.
- `std::vector` for audit records and alerts.
- `std::optional` for events that do not generate alerts.

The SHA-256 implementation demonstrates the mechanics of a cryptographic hash chain without requiring an external library.

For production cryptographic applications, a maintained cryptographic library should be preferred over custom cryptographic code.

### Complexity considerations

| Operation | Expected complexity |
|---|---|
| Event-ID lookup | Average O(1) |
| Role lookup | Average O(1) |
| Permission membership | O(log R) using `std::set` |
| Audit append | Amortized O(1), excluding hashing |
| Hash verification | O(N) |
| Statistical anomaly detection | O(N) |
| Alert lookup | O(A) in the sample implementation |

Here, N is the number of audit records, R is the number of roles or permissions, and A is the number of alerts.

### Execution

Compile:

`g++ -std=c++17 -O2 -Wall -Wextra -pedantic security_monitoring.cpp -o security_monitoring`

Run:

`./security_monitoring`

The implementation does not require external libraries.

## 9. Java 17 Implementation

The Java implementation follows an enterprise-oriented service architecture.

It separates the security domain, audit persistence abstraction, access policies, anomaly detection, alert management, and event orchestration.

### Service architecture

| Service | Responsibility |
|---|---|
| `AuditService` | Records and verifies audit events |
| `RoleBasedAccessPolicy` | Evaluates resource permissions |
| `AnomalyDetectionService` | Identifies suspicious activity |
| `AlertManagementService` | Manages alert states |
| `SecurityMonitoringService` | Coordinates event processing |
| `HashUtility` | Calculates SHA-256 digests |

### Java-specific mechanisms

- Records represent immutable domain objects.
- Enums restrict event, severity, and status values.
- Interfaces define access-policy behavior.
- Collections maintain role, permission, and event state.
- Streams support aggregation and reporting.
- `Optional` represents the absence of an alert.
- Custom exceptions distinguish audit and authorization failures.
- Synchronized service methods protect shared in-memory state.

The alert service creates replacement immutable alert records when state changes.

The audit service verifies the previous-hash relationship for every record.

The implementation also validates event attribute sizes and copies structured event details to prevent callers from modifying the original map after construction.

### Execution

Compile:

`javac SecurityMonitoring.java`

Run:

`java SecurityMonitoring`

Only Java 17 standard-library functionality is required.

## 10. PostgreSQL Implementation

The PostgreSQL implementation models a relational security monitoring platform.

It provides persistent relationships between organizations, systems, users, permissions, audit records, access decisions, alerts, and investigation evidence.

### 10.1 Relational architecture

| Table | Purpose |
|---|---|
| `organizations` | Organization ownership |
| `monitored_systems` | Systems under monitoring |
| `security_users` | User identities |
| `security_roles` | Role definitions |
| `user_role_assignments` | User-to-role relationships |
| `resource_permissions` | Role-to-resource permissions |
| `audit_logs` | Immutable event records |
| `access_logs` | Authorization decisions |
| `detection_rules` | Detection thresholds |
| `security_alerts` | Alert records |
| `alert_evidence` | Alert-to-event relationships |
| `alert_investigations` | Investigation decisions |

### 10.2 Referential integrity

Primary keys identify individual records.

Foreign keys establish valid relationships between organizations, systems, users, roles, permissions, audit events, and alerts.

Unique constraints prevent duplicate organizational identities and event identifiers.

Check constraints restrict invalid account states, severity scores, event attributes, and permission values.

The partial unique index on `user_role_assignments` prevents duplicate active assignments while preserving historical revoked assignments.

### 10.3 Indexing strategy

The project creates indexes for frequently used access patterns:

- Organization and system identification.
- Recent audit activity.
- User activity timelines.
- Event-type filtering.
- Source-IP investigation.
- Alert severity and status.
- Investigation history.
- JSONB event attributes.

The GIN index on `audit_logs.details` supports structured JSONB searches.

Indexes improve selected retrieval operations but introduce storage overhead and additional write costs.

Actual production indexes should be validated against query plans and representative workloads.

### 10.4 Database triggers

Three major integrity mechanisms are demonstrated.

**Audit immutability**

`trg_audit_immutable` rejects updates and deletions of audit records.

**Audit insertion validation**

`trg_validate_audit_insert` validates system ownership, organization relationships, user ownership, event-specific attributes, and hash-chain predecessor relationships.

**Access decision validation**

`trg_validate_access` checks that the access log references the correct audit event and that an allowed operation is consistent with the current authorization policy.

**Alert state validation**

`trg_alert_transition` prevents modification of terminal alerts and requires an assigned analyst for investigations.

These triggers enforce data-integrity rules at the database layer rather than depending exclusively on application behavior.

### 10.5 Functions and procedures

| Database object | Responsibility |
|---|---|
| `record_security_event` | Insert a structured audit event |
| `check_access_permission` | Evaluate user permissions |
| `evaluate_access` | Return ALLOW or DENY |
| `detect_security_anomalies` | Evaluate configured detection thresholds |
| `create_alert_from_event` | Create alerts and associate evidence |

The reporting views provide alert dashboards, access activity, and hourly event metrics.

The CTE-based evaluation query combines authentication failures, source-address diversity, and export activity into a user-level risk score.

### 10.6 Transactions

The SQL script uses a transaction to group schema creation, sample data insertion, and reporting demonstrations.

The alert-state demonstration also uses a nested PL/pgSQL exception block to isolate a failed operation without aborting the surrounding transaction.

Production event ingestion should use a transaction that preserves the audit event, related access record, detection outcome, and alert evidence consistently.

### 10.7 PostgreSQL compatibility

The script uses PostgreSQL-native types and functionality, including:

- `JSONB`
- `INET`
- `UUID`
- `TIMESTAMPTZ`
- Identity columns
- Partial indexes
- Filtered aggregates
- Common Table Expressions
- PL/pgSQL triggers
- Stored procedures

The example uses `gen_random_uuid()` for alert identifiers. PostgreSQL installations must provide that function, commonly through the `pgcrypto` extension.

The sample audit hashes demonstrate hash-chain linkage. The SQL trigger checks the predecessor relationship but does not independently calculate or authenticate SHA-256 values.

For cryptographic verification, the application should calculate canonical event hashes using a consistent serialization format and independently verify the chain.

## 11. Security Monitoring Workflow

The implementations use the following operational sequence:

### Event collection

Applications and monitored services generate structured events.

Each event should contain a reliable timestamp, event identifier, actor, source, resource, outcome, and relevant contextual information.

### Validation

The monitoring layer checks event structure, required attributes, identifier uniqueness, and valid event types.

Malformed or oversized events are rejected.

### Audit recording

Validated events are recorded before anomaly evaluation.

This preserves an evidence trail even when no alert is generated.

### Access evaluation

Access decisions are evaluated independently using identity, role, resource, and permission information.

A successful authorization decision must agree with the applicable permission policy.

### Detection

The monitoring engine evaluates configured thresholds and behavioral indicators.

Events can trigger multiple anomaly categories.

### Alert generation

Anomalous activity creates an alert containing the detection category, severity, score, and evidence reference.

### Investigation

An analyst receives the alert, reviews the associated evidence, and records an investigation decision.

### Resolution

The alert is resolved when the investigation is complete or classified as a false positive when the observed condition is not a security incident.

## 12. Failure Modes and Edge Cases

| Condition | Expected handling |
|---|---|
| Duplicate event ID | Reject duplicate ingestion |
| Invalid timestamp | Reject malformed event |
| Missing user identity | Reject invalid event |
| Unknown user | Deny authorization |
| Unknown resource | Deny authorization |
| Insufficient permission | Record denied access |
| Unauthorized successful access record | Reject inconsistent event |
| Excessive event attributes | Reject oversized event |
| Repeated login failures | Generate anomaly |
| Large data export | Evaluate export threshold |
| Privilege modification | Generate security alert |
| Zero statistical deviation | Avoid division by zero |
| Modified audit record | Fail hash-chain verification |
| Missing investigation analyst | Reject investigation transition |
| Modification of closed alert | Reject state change |
| Inactive monitored system | Reject new audit ingestion |

An important operational distinction is that an invalid event is not equivalent to a failed security event.

Invalid events should be rejected or quarantined, while legitimate denied access attempts should be preserved as security evidence.

## 13. Performance and Scalability

The examples use in-memory collections for portability and educational clarity.

These implementations are not distributed security information and event management platforms.

Production environments require additional architecture.

### Event ingestion

High-volume systems should use durable ingestion queues and controlled batch processing.

Event consumers should support retries and idempotency.

### Storage

Audit records should be stored in durable, access-controlled systems.

Time-based partitioning can reduce the cost of managing large historical event tables.

Retention and archival policies should consider regulatory requirements and investigation needs.

### Detection

Sliding-window detection is suitable for recent event correlation.

Large deployments should partition detection state by user, tenant, monitored system, or other appropriate keys.

Expensive statistical analysis can operate asynchronously against aggregated observations.

### Alert management

Alert deduplication prevents repeated notifications for the same underlying condition.

Correlation identifiers and incident grouping help analysts investigate related events efficiently.

### Reporting

Hourly aggregation and selective indexing reduce the need to repeatedly scan raw events.

Materialized views can support expensive reporting workloads when refresh consistency requirements permit.

## 14. Security and Governance Considerations

The project demonstrates technical monitoring controls, but a production implementation requires broader governance.

Important controls include:

- Strong authentication for monitoring administrators.
- Multi-factor authentication for privileged accounts.
- Least-privilege access to audit records.
- Separation of duties between system administrators and auditors.
- Encryption in transit and at rest.
- Secure timestamp synchronization.
- Protected audit retention.
- Centralized log collection.
- Restricted access to personally identifiable information.
- Controlled retention and deletion procedures.
- Alert assignment and investigation accountability.
- Detection-rule change management.
- Monitoring of monitoring-system failures.

Sensitive credentials, passwords, access tokens, and authentication secrets should never be included in ordinary audit-event details.

Source IP addresses and user identifiers can constitute sensitive operational information and should be protected according to organizational privacy requirements.

A security alert should not automatically trigger account suspension or destructive remediation without an appropriate policy and authorization mechanism.

## 15. Limitations of the Demonstration

The implementations deliberately use transparent detection rules and sample data.

They do not provide:

- Distributed log collection.
- Production-grade event streaming.
- Full geographic anomaly detection.
- Machine-learning-based behavioral profiling.
- Enterprise identity-provider integration.
- Automated incident containment.
- Distributed transaction coordination.
- Cryptographic signatures and external audit anchoring.
- Complete regulatory compliance.
- Production-grade multi-tenant isolation.

The hash-chain implementations demonstrate tamper detection, not guaranteed non-repudiation.

The statistical detector demonstrates numerical deviation analysis, not a complete behavioral baseline.

The PostgreSQL rule engine demonstrates threshold evaluation. Its example procedure uses a simplified score mapping rather than the full in-memory scoring algorithm.

The SQL audit hash values in the sample records are illustrative linkage values, not cryptographically verified event digests.

## 16. Technical Comparison

| Capability | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Structured events | Dataclasses | Objects | Structs | Records | Relational tables |
| Access control | RBAC class | Policy class | Policy engine | Policy interface | SQL functions |
| Audit integrity | SHA-256 chain | SHA-256 chain | SHA-256 chain | SHA-256 chain | Hash linkage validation |
| Anomaly detection | Sliding window | Sliding window | Sliding window | Sliding window | SQL thresholds |
| Statistical detection | Z-score | Z-score | Z-score | Z-score | Aggregation |
| Alert management | Dataclass state | Alert manager | Alert engine | Alert service | Alert tables |
| Validation | Exceptions | Type checks | Exceptions | Custom exceptions | Constraints and triggers |
| Persistence | JSONL export | JSONL export | In-memory | In-memory | Relational storage |
| Concurrency model | Sequential simulator | Promise serialization | Single-threaded simulator | Synchronized services | Transactional |

## 17. Important Terminology

| Term | Meaning |
|---|---|
| Audit Trail | Chronological evidence of system activity |
| Access Log | Record of access requests and authorization outcomes |
| RBAC | Role-Based Access Control |
| SIEM | Security Information and Event Management |
| IOC | Indicator of Compromise |
| Anomaly | Activity that differs from an expected pattern |
| False Positive | Alert that does not represent the suspected security condition |
| False Negative | Actual security condition that was not detected |
| Event Correlation | Association of related events to identify a broader activity pattern |
| Hash Chain | Sequence of records linked through cryptographic hashes |
| Least Privilege | Restricting permissions to the minimum necessary |
| Sliding Window | Analysis of events within a moving time interval |
| Z-Score | Standardized measurement of deviation from a statistical mean |
| Incident Investigation | Examination of security evidence to determine the nature and impact of an event |
| Log Retention | Controlled preservation of historical records |
| Alert Deduplication | Prevention of repeated alerts for the same underlying condition |

## 18. Execution and File Organization

The five source implementations are independent.

| File | Runtime |
|---|---|
| `security_monitoring.py` | Python 3.10+ |
| `security_monitoring.js` | Node.js 18+ |
| `security_monitoring.cpp` | C++17 |
| `SecurityMonitoring.java` | Java 17 |
| `security_monitoring.sql` | PostgreSQL 14+ |

The PostgreSQL script should be executed against a database in which the required UUID-generation function is available.

The programs include sample security events and executable assertions or tests for core monitoring behavior.

Each implementation can be studied independently while preserving the same domain distinctions between audit evidence, access decisions, anomaly detection, and security alerts.
