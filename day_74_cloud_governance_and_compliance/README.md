# Cloud Governance and Compliance Management

## 1. Domain Overview

Cloud Governance and Compliance is the structured management of cloud infrastructure, organizational policies, regulatory obligations, security controls, operational responsibilities, and evidence of compliance.

Organizations use cloud governance to establish how cloud resources are provisioned, configured, accessed, monitored, assessed, and maintained.

Cloud governance addresses questions such as:

- Which cloud resources exist?
- Who owns each resource?
- Where is organizational data stored?
- What classification applies to the data?
- Which security controls must be enforced?
- Which regulatory obligations apply?
- How are policy violations identified?
- Who can authorize remediation?
- How can compliance decisions be independently verified?

The five implementations represent complementary approaches to these problems using Python, JavaScript, C++17, Java 17, and PostgreSQL.

## 2. Core Concepts

### 2.1 Cloud Governance

Cloud governance is the organizational framework that defines acceptable cloud usage and establishes accountability.

It combines:

| Area | Responsibility |
|---|---|
| Organizational governance | Defines authority, ownership and accountability |
| Resource governance | Maintains cloud inventory and ownership |
| Security governance | Defines encryption, access and logging requirements |
| Data governance | Controls classification, retention and handling |
| Regulatory governance | Maps external obligations to internal controls |
| Financial governance | Establishes budgets and resource cost accountability |
| Operational governance | Defines monitoring, backup and remediation procedures |
| Audit governance | Maintains evidence and accountability |

Governance establishes the rules and responsibilities. Compliance assessment determines whether actual configurations satisfy those rules.

### 2.2 Governance Versus Compliance

These concepts are related but different.

**Governance** defines what an organization requires.

**Compliance** measures whether the organization meets applicable requirements.

For example:

- Governance establishes that restricted databases must use encryption.
- A policy translates this requirement into an evaluable condition.
- A compliance assessment inspects the database configuration.
- A finding records an unsuccessful evaluation.
- A remediation request establishes corrective action.
- A subsequent assessment verifies the resulting configuration.

A resource can be technically secure but still fail an organizational policy. Conversely, a resource can satisfy a particular technical policy without satisfying every regulatory obligation.

### 2.3 Cloud Resource Inventory

A cloud resource represents an identifiable infrastructure or platform object.

The implementations model four resource categories:

| Resource type | Examples | Governance concerns |
|---|---|---|
| Storage | Object storage, file storage | Encryption, public exposure, retention |
| Database | Relational and document databases | Access, backups, encryption, residency |
| Compute | Virtual machines and application instances | Patching, identity, network exposure |
| Network | Virtual networks and security boundaries | Segmentation, connectivity, access |

Each resource has:

- Unique resource identifier
- Resource name
- Cloud provider
- Cloud region
- Resource owner
- Data classification
- Encryption configuration
- Public-access configuration
- Backup configuration
- Organizational metadata

The inventory is the foundation for policy enforcement and compliance assessment.

### 2.4 Data Classification

Classification establishes the sensitivity of information and determines which governance controls apply.

| Classification | Meaning | Typical controls |
|---|---|---|
| PUBLIC | Approved for public distribution | Integrity and availability |
| INTERNAL | Intended for organizational use | Identity and access management |
| CONFIDENTIAL | Sensitive organizational information | Encryption and restricted access |
| RESTRICTED | Highly sensitive or regulated information | Strong encryption, strict access, backup and residency controls |

Classification-aware policies prevent unnecessary enforcement against resources to which a particular requirement does not apply.

For example, a restricted-data encryption policy should not automatically classify every public documentation resource as non-compliant.

Classification must be assigned using an organization's documented data-classification rules rather than inferred solely from resource names.

---

## 3. Governance Policies

### 3.1 Policy Definition

A governance policy expresses a condition that cloud resources must satisfy.

The implementations include four primary policy categories.

| Policy | Requirement | Typical severity |
|---|---|---|
| ENC-001 | Sensitive information must be encrypted | Critical |
| PUB-001 | Sensitive resources must not be publicly exposed | Critical |
| BKP-001 | Restricted resources must have backups | High |
| REG-001 | Restricted resources must use approved regions | Critical |
| LOG-001 | Restricted resources must have security logging | High |

A policy consists of:

- Unique identifier
- Name
- Description
- Severity
- Applicability conditions
- Required security properties
- Permitted configuration values

Policies are evaluated independently.

This makes it possible to identify multiple failures on a single resource rather than returning only one general compliance result.

### 3.2 Policy Evaluation

The policy evaluation process compares the actual resource configuration with the expected configuration.

The logical workflow is:

Resource inventory  
→ Classification  
→ Policy applicability  
→ Configuration inspection  
→ Rule evaluation  
→ Compliance result  
→ Finding creation

Each policy produces one of three results.

| Result | Interpretation |
|---|---|
| COMPLIANT | Applicable policy requirements are satisfied |
| NON_COMPLIANT | One or more requirements are violated |
| NOT_APPLICABLE | The policy does not apply to the resource |

The distinction between non-compliance and non-applicability is important.

A policy that does not apply should not be counted as a failed control.

### 3.3 Severity and Risk

Severity represents the organizational importance of a policy violation.

The implementations use four levels:

1. LOW
2. MEDIUM
3. HIGH
4. CRITICAL

Severity can support remediation prioritization.

A practical prioritization model considers:

- Data sensitivity
- External exposure
- Potential impact
- Regulatory implications
- Exploitability
- Resource criticality
- Duration of the violation

Severity alone is not a complete risk assessment. A production risk model should also consider likelihood, business impact and existing compensating controls.

---

## 4. Regulatory Frameworks and Control Mapping

### 4.1 Regulatory Frameworks

A regulatory framework establishes requirements that organizations may need to satisfy based on their jurisdiction, industry, activities and processing of information.

The SQL implementation includes illustrative framework records for:

| Framework | Scope |
|---|---|
| GDPR | European Union personal data protection |
| ISO/IEC 27001:2022 | Information security management systems |
| Digital Personal Data Protection Act, 2023 | India's personal data protection framework |

These frameworks are not interchangeable.

GDPR is a legal regulatory framework. ISO/IEC 27001 is an international management-system standard. India's Digital Personal Data Protection Act is legislation.

Their applicability and individual obligations depend on the organization, processing activities, jurisdiction and current legal requirements.

### 4.2 Regulatory Controls

A regulatory control represents a specific obligation or control statement associated with a framework.

The database separates:

- Regulatory framework
- Regulatory control
- Internal governance policy
- Policy-to-control mapping
- Assessment result

This separation prevents an internal technical policy from being incorrectly treated as the complete regulatory framework.

### 4.3 Control Mapping

Control mapping establishes a documented relationship between internal security requirements and external obligations.

For example:

Internal encryption policy  
→ Encryption control  
→ Regulatory control mapping  
→ Evidence from cloud resource configuration  
→ Assessment result

One internal policy can support multiple regulatory controls.

One regulatory control can also be supported by multiple internal policies.

The `policy_control_mappings` table implements this many-to-many relationship.

A mapping establishes traceability. It does not independently prove that the organization satisfies the mapped regulation.

---

## 5. Data Residency and Sovereignty

### 5.1 Data Residency

Data residency describes the geographic location in which information is stored or processed.

A residency requirement can establish:

- Approved storage regions
- Prohibited regions
- Applicable data classifications
- Effective dates
- Organizational scope
- Associated regulatory obligations

The implementations use explicit regional allowlists.

For example, an organization may define:

- `ap-south-1`
- `ap-south-2`

as approved locations for restricted information.

A resource deployed in another region fails that particular organizational residency rule.

### 5.2 Data Residency Versus Data Sovereignty

These terms are related but distinct.

| Concept | Meaning |
|---|---|
| Data residency | Geographic location where data is stored or processed |
| Data sovereignty | Legal jurisdiction and authority governing information |
| Data localization | Requirements to retain certain information within a specified territory |
| Data transfer | Movement or access of information across geographic or legal boundaries |

Physical storage location does not, by itself, establish every legal jurisdiction governing the data.

Organizations must consider the provider, processing arrangements, access locations, contractual commitments and applicable legislation.

### 5.3 Residency Evaluation

The residency evaluator checks:

1. The resource's classification.
2. The applicable residency rule.
3. The resource's actual region.
4. The permitted region list.
5. Any explicitly prohibited regions.
6. The rule's effective period.

The evaluation produces an independent residency result.

This is important because encryption compliance and residency compliance are different dimensions.

An encrypted database can still violate an organization's residency requirements.

---

## 6. Encryption and Access Governance

### 6.1 Encryption at Rest

Encryption at rest protects stored information.

Examples include:

- Database storage encryption
- Object storage encryption
- Disk encryption
- Backup encryption

The implementations use the `encrypted_at_rest` or equivalent resource property to demonstrate a policy decision.

The sample implementations treat encryption as a configuration requirement. They do not perform actual cryptographic encryption of cloud data.

### 6.2 Encryption in Transit

Encryption in transit protects information transmitted between systems.

Examples include:

- TLS-protected APIs
- Encrypted database connections
- Secure service-to-service communication
- Protected administrative connections

The SQL inventory records both encryption at rest and encryption in transit.

These controls should be assessed independently because satisfying one does not guarantee the other.

### 6.3 Public Access Prevention

Public exposure is a significant cloud security concern.

Examples include:

- Public database endpoints
- Unrestricted object storage
- Excessively permissive network rules
- Unauthenticated administrative services

The `prohibit_public_access` policy checks whether a resource has public access enabled.

A production implementation should also inspect effective network permissions, identity policies, firewall rules and service-specific access configurations.

### 6.4 Backup Governance

Backup governance addresses:

- Backup availability
- Recovery objectives
- Retention
- Backup encryption
- Geographic restrictions
- Restoration testing
- Backup access permissions

The sample implementation checks whether backup is enabled.

It does not independently establish that backups are recoverable or satisfy a specific retention or recovery-time requirement.

---

## 7. Python Implementation

**File:** `cloud_governance.py`

### 7.1 Architecture

The Python implementation uses an object-oriented governance simulation.

| Component | Responsibility |
|---|---|
| `CloudResource` | Represents cloud infrastructure |
| `GovernancePolicy` | Defines policy requirements |
| `PolicyEngine` | Evaluates resource configurations |
| `PolicyResult` | Stores assessment outcomes |
| `DataResidencyPolicy` | Checks geographic restrictions |
| `AuditLogger` | Maintains hash-linked audit events |
| `GovernanceService` | Coordinates governance operations |

### 7.2 Dataclasses and Enumerations

Dataclasses provide structured domain records.

Enumerations constrain valid resource types, severity levels, classification values and assessment states.

The `GovernancePolicy` dataclass is immutable.

This prevents accidental modification of policy definitions after they have been registered.

### 7.3 Dictionaries and Lists

The governance service maintains:

- A dictionary of resources indexed by resource identifier.
- A dictionary of assessment results indexed by resource identifier.
- Lists of policy definitions and audit events.

Dictionary-based lookup provides average-case constant-time resource retrieval.

Policy evaluation is proportional to the number of policies evaluated against a resource.

For `R` resources and `P` policies, a full inventory evaluation requires approximately:

`O(R × P)`

This excludes additional costs associated with audit persistence and external cloud API calls.

### 7.4 Audit Integrity

The Python audit logger calculates SHA-256 hashes for audit events.

Each event references the preceding event hash.

The resulting structure is:

`Event 1 → Event 2 → Event 3 → Event 4`

Changing an earlier event invalidates the subsequent hash verification.

This provides tamper-evidence within the recorded chain.

It is not a substitute for externally protected, immutable audit storage. An attacker who can modify the entire event collection and recompute the hashes can construct another valid chain.

### 7.5 Remediation

The remediation service supports three configuration changes:

- Enable encryption.
- Disable public access.
- Enable backups.

Changes are explicitly requested and recorded in the audit history.

The demonstration assesses the customer database, identifies violations, applies remediation and performs another assessment.

The report distinguishes applicable policy evaluations from non-applicable policies.

### 7.6 Output

The application produces:

- Resource-level policy results
- Residency decisions
- Violation descriptions
- Remediation activity
- Compliance percentages
- Audit integrity results
- A JSON compliance report

The report is written to `cloud_compliance_report.json`.

---

## 8. JavaScript Implementation

**File:** `cloud_governance.js`

### 8.1 Architecture

The JavaScript implementation emphasizes event-driven execution and asynchronous operational workflows.

| Component | Responsibility |
|---|---|
| `CloudResource` | Validates cloud resource data |
| `Policy` | Evaluates individual governance rules |
| `AuditService` | Records audit events |
| `ResidencyService` | Evaluates regional restrictions |
| `GovernanceEventBus` | Distributes governance events |
| `GovernanceEngine` | Coordinates assessment and remediation |

### 8.2 Maps and Sets

The implementation uses `Map` for resource inventories and assessment records.

A map provides efficient resource lookup using identifiers.

`Set` is used for:

- Approved regions
- Applicable classifications
- Regulatory configuration

Sets prevent duplicate entries and provide efficient membership checks.

### 8.3 Asynchronous Operations

The implementation uses asynchronous methods for:

- Resource registration
- Audit recording
- Event publication
- Remediation
- File exports

The `async` and `await` structure allows these operations to be extended to cloud APIs and external services without blocking the overall application architecture.

### 8.4 Event-Driven Governance

A governance event bus distributes policy violations.

For example:

Policy evaluation  
→ Violation detected  
→ Audit event created  
→ Event published  
→ Alert listener processes violation

This separates policy evaluation from downstream notification.

A production deployment could connect such events to incident-management systems, ticketing platforms, security monitoring or notification services.

### 8.5 Remediation Validation

The remediation workflow creates a candidate resource configuration before committing the requested changes.

It validates the proposed boolean properties before modifying the resource.

The authorization check prevents ordinary users from initiating administrative remediation.

The demonstration intentionally tests an unauthorized request.

### 8.6 Output Files

The JavaScript implementation produces:

- `cloud_governance_audit.json`
- `cloud_governance_report.json`

The audit export uses restrictive file permissions where supported by the operating system.

---

## 9. C++17 Implementation

**File:** `cloud_governance.cpp`

### 9.1 Architecture

The C++ implementation focuses on explicit domain modeling, deterministic policy evaluation and controlled state management.

| Component | Responsibility |
|---|---|
| `CloudResource` | Represents infrastructure |
| `Policy` | Defines policy configuration |
| `PolicyEvaluator` | Executes governance rules |
| `ResidencyEvaluator` | Checks approved regions |
| `AuditLogger` | Records chained events |
| `GovernanceReport` | Stores aggregate results |
| `GovernanceEngine` | Coordinates system operations |

### 9.2 STL Data Structures

The implementation uses:

| Structure | Application |
|---|---|
| `vector` | Policies, results and audit records |
| `map` | Resource inventory and assessment records |
| `set` | Approved regions and applicable classifications |
| `string` | Identifiers and configuration values |

The resource inventory uses `std::map`.

Its lookup, insertion and deletion operations generally have logarithmic complexity.

For a large inventory requiring average-case constant-time lookup, `std::unordered_map` could be considered.

### 9.3 Domain Validation

The implementation uses explicit validation functions and custom exceptions.

Invalid identifiers, missing ownership information and duplicate resource identifiers are rejected.

The exception hierarchy separates:

- General governance failures
- Validation failures
- Authorization failures
- Resource lookup failures

### 9.4 State Management

The remediation engine uses a candidate copy of the resource.

The candidate is validated before replacing the existing resource.

This reduces the possibility of partially applying invalid changes.

After remediation, the previous assessment is invalidated.

A new assessment is required to establish the current compliance state.

### 9.5 Performance Considerations

The implementation uses:

- Container-based indexed lookup
- Iterative policy evaluation
- Classification-based applicability
- Structured result collection
- Separate reporting aggregation

For `R` resources and `P` policies, complete assessment remains approximately `O(R × P)`.

The sample implementation uses an educational non-cryptographic hash for its C++ audit chain.

This is an intentional limitation: `std::hash` is not a cryptographic integrity mechanism and must not be used to secure production audit records.

A production implementation should use a vetted SHA-256 or SHA-3 implementation and externally protected audit storage.

---

## 10. Java 17 Implementation

**File:** `CloudGovernance.java`

### 10.1 Enterprise Domain Architecture

The Java implementation models governance as an enterprise service with explicit domain types.

It uses:

- Records
- Interfaces
- Abstract classes
- Enums
- Immutable collections
- Concurrent maps
- Custom exceptions
- Service classes
- Policy objects

### 10.2 Interface-Based Policy Design

`GovernancePolicy` defines the common policy contract.

Each policy provides:

- A policy identifier
- A name
- A severity
- Applicability conditions
- A resource validation method

The abstract policy class provides common metadata and classification-based applicability.

Concrete policy implementations separately handle encryption, public access, backup and region restrictions.

This design supports adding new policies without placing every policy condition inside one large service method.

### 10.3 Immutable Records

Java records represent:

- Cloud resources
- Policy results
- Regulatory controls
- Residency results
- Approvals
- Remediation requests
- Assessment results
- Compliance reports
- Audit events

The resource model uses immutable fields.

Remediation creates an updated resource record rather than modifying the original object.

This makes state transitions easier to inspect and validate.

### 10.4 Approval-Controlled Remediation

The enterprise service separates remediation intent from remediation authorization.

The remediation request describes the proposed changes.

The approval record captures:

- Reviewer identity
- Reviewer role
- Approval decision
- Justification

The demonstration requires an approved security or governance administrator.

It also demonstrates rejection when an unauthorized reviewer attempts remediation.

The sample is a single-approval workflow. A production enterprise system should support configurable approval thresholds, independent reviewer identities, segregation of duties and approval expiry.

### 10.5 Streams and Reporting

Java streams aggregate assessment results.

The reporting service calculates:

- Total resources
- Assessed resources
- Total policy evaluations
- Compliant evaluations
- Non-compliant evaluations
- Non-applicable evaluations
- Residency violations
- Compliance percentage

This separates reporting from individual policy implementations.

---

## 11. PostgreSQL Implementation

**File:** `cloud_governance.sql`

### 11.1 Relational Architecture

The database provides persistent governance records and supports historical compliance reporting.

The schema is named `cloud_governance`.

The principal relationship is:

`Organization`
→ `Users`
→ `Cloud Resources`
→ `Governance Policies`
→ `Assessment Runs`
→ `Policy Evaluations`
→ `Compliance Findings`
→ `Remediation Requests`
→ `Approvals`

Regulatory obligations follow a separate relationship:

`Regulatory Framework`
→ `Regulatory Controls`
→ `Policy Control Mappings`

Residency is represented independently:

`Residency Rules`
→ `Residency Evaluations`

Audit history is maintained separately from operational resource records.

### 11.2 Relational Tables

| Table | Purpose |
|---|---|
| `organizations` | Organizational identity |
| `governance_users` | Users and governance roles |
| `cloud_providers` | Cloud provider registry |
| `cloud_resources` | Infrastructure inventory |
| `regulatory_frameworks` | Regulatory framework definitions |
| `regulatory_controls` | Individual framework controls |
| `residency_rules` | Geographic data restrictions |
| `governance_policies` | Internal policy definitions |
| `policy_control_mappings` | Regulatory traceability |
| `assessment_runs` | Assessment execution history |
| `policy_evaluations` | Policy evaluation results |
| `residency_evaluations` | Residency evaluation results |
| `compliance_findings` | Recorded violations |
| `remediation_requests` | Corrective action requests |
| `remediation_approvals` | Approval decisions |
| `audit_events` | Operational audit history |

### 11.3 Integrity Constraints

The schema uses primary keys and foreign keys to maintain relational consistency.

Unique constraints prevent duplicate organizational users, resource identifiers, policy codes and regulatory control mappings.

Check constraints validate:

- Accepted user roles
- Resource names
- Region values
- JSON document types
- Assessment states
- Residency effective dates

Foreign keys prevent records from referencing nonexistent organizations, users, policies and resources.

### 11.4 JSONB

JSONB stores structured information that may vary between policies and assessment results.

Examples include:

- Resource tags
- Violation details
- Proposed remediation changes
- Audit event details
- Residency evaluation evidence

Relational columns remain responsible for identifiers, ownership, relationships and frequently queried attributes.

JSONB should not replace relational constraints for important governance relationships.

### 11.5 Policy Evaluation Function

`evaluate_cloud_resource()` executes active organizational policies against an individual resource.

It checks:

- Encryption
- Public exposure
- Backup
- Security logging
- Approved regions
- Classification applicability

The function writes one result per resource and policy combination.

The unique constraint on assessment, resource and policy prevents duplicate evaluation records within the same assessment.

### 11.6 Residency Evaluation Function

`evaluate_data_residency()` evaluates resource regions against active residency rules.

It uses:

- Organizational ownership
- Data classification
- Permitted regions
- Prohibited regions
- Effective dates

Residency evaluation is separate from ordinary policy evaluation.

### 11.7 Stored Procedure

`run_resource_assessment()` coordinates an individual assessment.

Its workflow is:

1. Identify the resource.
2. Verify the requesting user's organizational membership.
3. Validate the user's role.
4. Create an assessment record.
5. Execute policy evaluation.
6. Execute residency evaluation.
7. Mark the assessment complete.
8. Record an audit event.

The procedure uses the surrounding transaction so an unsuccessful assessment does not leave a partially committed workflow.

### 11.8 Remediation Approval

The remediation workflow separates requests from approval decisions.

The `remediation_requests` table stores the proposed corrective action.

The `remediation_approvals` table records the reviewer and decision.

The approval trigger enforces two important conditions:

- The requester cannot approve their own request.
- Only designated security or compliance roles can approve remediation.

`determine_remediation_decision()` evaluates recorded decisions and updates the request status.

The example uses a simplified approval model. A real deployment should define approval thresholds, multiple reviewer requirements, role scope and rejection-handling rules.

### 11.9 Indexing

The database defines indexes for common governance queries.

| Index | Purpose |
|---|---|
| Organization index | Resource isolation and retrieval |
| Classification index | Classification-based policy evaluation |
| Region index | Residency assessments |
| Provider-region index | Cloud inventory analysis |
| Assessment-status index | Compliance reporting |
| Resource-evaluation index | Historical resource assessment |
| Open-findings index | Remediation prioritization |
| Audit-time index | Audit investigation |
| JSONB GIN index | Resource tag filtering |

Partial indexes are used for active resources and unresolved findings.

This reduces index size when queries consistently target those subsets.

### 11.10 Views

The SQL implementation includes four principal reporting views.

**`v_resource_posture`**

Displays resource configuration, provider, region, classification and owner.

**`v_policy_compliance`**

Combines assessment results with policy definitions and resource information.

**`v_open_remediation`**

Displays remediation items that have not been resolved or rejected.

**`v_assessment_summary`**

Aggregates compliant, non-compliant and non-applicable evaluations.

These views simplify reporting without duplicating the underlying records.

---

## 12. Audit Logging and Evidence Management

### 12.1 Audit Events

An audit event records a governance-related action.

Examples include:

- Resource registration
- Policy evaluation
- Violation detection
- Remediation creation
- Remediation approval
- Remediation rejection
- Remediation completion

A useful audit record should identify:

- What happened
- Who performed the action
- Which resource was affected
- When the action occurred
- What decision or configuration was involved

### 12.2 Hash-Linked Audit Records

The implementations demonstrate a chained event structure.

Each event contains the preceding event's hash.

Conceptually:

`H1 = SHA256(Event1)`

`H2 = SHA256(Event2 + H1)`

`H3 = SHA256(Event3 + H2)`

This allows subsequent verification of event integrity.

The implementations have different security properties:

| Implementation | Hash approach |
|---|---|
| Python | SHA-256 |
| JavaScript | Node.js SHA-256 |
| C++17 | Educational non-cryptographic demonstration hash |
| Java 17 | Java SHA-256 |
| PostgreSQL | pgcrypto SHA-256 |

Hash chaining alone does not make a database immutable.

Production audit architecture should use:

- Restricted write permissions
- Separation of audit administration
- Independent log storage
- Protected audit exports
- Time synchronization
- Retention controls
- Monitoring for privileged changes
- Periodic integrity verification

### 12.3 Evidence

Compliance evidence should support the actual decision being reported.

Examples include:

- Resource configuration snapshots
- Encryption configuration
- Identity and access policies
- Residency configuration
- Backup configuration
- Assessment results
- Approval records
- Audit events

An assessment result without supporting evidence may be insufficient for an external audit.

---

## 13. Remediation Lifecycle

A governance finding should progress through a controlled operational workflow.

The lifecycle is:

`Detection`
→ `Finding`
→ `Remediation Request`
→ `Assignment`
→ `Approval`
→ `Implementation`
→ `Reassessment`
→ `Resolution`

### 13.1 Finding Creation

A finding records a specific failed requirement.

It should contain:

- Finding identifier
- Related resource
- Related policy
- Severity
- Description
- Detection timestamp
- Current remediation status

### 13.2 Remediation Request

A remediation request defines the proposed corrective action.

Examples:

- Enable encryption.
- Disable public access.
- Enable backups.
- Move a resource to an approved region.
- Enable security logging.

### 13.3 Approval

Approval establishes whether the proposed change is authorized.

The approval decision should be separate from the remediation request itself.

This supports accountability and segregation of duties.

### 13.4 Reassessment

A successful remediation action does not automatically prove compliance.

The resource must be evaluated again.

For example:

Initial assessment: Encryption failure.

Remediation: Enable encryption.

New assessment: Encryption requirement satisfied.

Only the new assessment establishes the updated policy result.

### 13.5 Resolution

A finding should be resolved only after the organization has verified the corrective action.

A rejected remediation request does not mean that the original compliance violation has disappeared.

---

## 14. Compliance Measurement

### 14.1 Compliance Percentage

The implementations use the following measurement:

`Compliance Percentage = (Compliant Applicable Evaluations / Total Applicable Evaluations) × 100`

For example:

| Result | Count |
|---|---:|
| Compliant | 36 |
| Non-compliant | 4 |
| Not applicable | 10 |
| Total | 50 |

Applicable evaluations:

`36 + 4 = 40`

Compliance percentage:

`(36 / 40) × 100 = 90%`

Not-applicable evaluations are excluded from the denominator.

### 14.2 Measurement Limitations

A compliance percentage does not establish that an organization is fully secure.

For example:

- A critical violation and a low-severity violation should not necessarily have equal operational priority.
- A missing assessment should not automatically be interpreted as compliance.
- A recently evaluated resource can become non-compliant after a configuration change.
- One control may have a greater business impact than another.
- Compliance with an internal policy does not automatically demonstrate legal compliance.

A production dashboard should report compliance percentage alongside critical findings, overdue remediation, assessment freshness, evidence completeness and resource coverage.

---

## 15. Security and Production Considerations

### 15.1 Identity and Access Management

Governance operations should follow least-privilege access.

| Role | Typical responsibility |
|---|---|
| Cloud administrator | Cloud resource administration |
| Security administrator | Security controls and remediation approval |
| Compliance officer | Compliance assessment and control oversight |
| Resource owner | Resource configuration and corrective action |
| Auditor | Evidence inspection and independent verification |
| Viewer | Read-only reporting |

Administrative privileges should be separated from ordinary assessment and reporting permissions.

### 15.2 Secrets Management

Cloud credentials should not be embedded in source code.

Production deployments should use managed identities, short-lived credentials, protected secret stores and restricted service accounts.

### 15.3 Resource Configuration Drift

A resource may become non-compliant after an assessment.

Examples include:

- A storage bucket becomes publicly accessible.
- Encryption is disabled.
- An unauthorized region is introduced.
- A backup configuration is removed.
- Security logging is disabled.

A governance platform should support scheduled assessment and event-triggered reassessment.

### 15.4 Multi-Cloud Governance

Cloud providers expose different resource configuration models.

A multi-cloud governance system should normalize common governance properties while retaining provider-specific evidence.

For example, the logical requirement may be identical:

`Encryption at rest = REQUIRED`

The actual configuration evidence and API operations may differ between providers.

A common resource model should not erase important provider-specific security differences.

### 15.5 Organizational Isolation

Multi-tenant governance systems must ensure that one organization cannot inspect or modify another organization's information.

The SQL model uses organization identifiers in core entities.

A production deployment should also enforce database permissions, tenant isolation and PostgreSQL Row-Level Security where appropriate.

Application-side filtering alone is not sufficient for strong tenant isolation.

### 15.6 Assessment Freshness

Compliance assessments should have a recorded execution time.

Organizations should establish freshness requirements based on resource sensitivity and operational risk.

A resource assessed several months ago should not be presented as having verified current compliance.

### 15.7 Database Security

The PostgreSQL implementation demonstrates integrity constraints and audit triggers.

A production database should additionally use:

- Separate application and administrative roles
- Restricted schema permissions
- TLS connections
- Encrypted storage and backups
- Secure credential rotation
- Audited privileged access
- Independent backup verification
- Controlled database migrations

---

## 16. Execution Requirements

| Deliverable | Runtime | External dependencies |
|---|---|---|
| Python | Python 3.10+ | None |
| JavaScript | Node.js 18+ | None |
| C++17 | C++17 compiler | None |
| Java | Java 17 | None |
| PostgreSQL | PostgreSQL 14+ | pgcrypto extension |

### Python

File: `cloud_governance.py`

Run:

`python cloud_governance.py`

The application generates `cloud_compliance_report.json`.

### JavaScript

File: `cloud_governance.js`

Run:

`node cloud_governance.js`

The application generates the audit and compliance JSON files.

### C++17

File: `cloud_governance.cpp`

Compile:

`g++ -std=c++17 -O2 -Wall -Wextra -pedantic cloud_governance.cpp -o cloud_governance`

Run:

`./cloud_governance`

On Windows:

`cloud_governance.exe`

### Java 17

File: `CloudGovernance.java`

Compile:

`javac CloudGovernance.java`

Run:

`java CloudGovernance`

### PostgreSQL

File: `cloud_governance.sql`

Execute using:

`psql -U postgres -d postgres -f cloud_governance.sql`

The executing database role must have permission to create the schema, tables, extension, functions and triggers.

The script uses the `pgcrypto` extension for SHA-256 audit hashing.

---

## 17. Testing and Validation Scenarios

The following scenarios represent the important behavior implemented across the five source files.

| Scenario | Expected behavior |
|---|---|
| Valid encrypted internal resource | Applicable policies pass |
| Restricted unencrypted database | Encryption violation |
| Sensitive public database | Public exposure violation |
| Restricted resource without backup | Backup violation |
| Restricted resource in unapproved region | Residency and region violation |
| Public resource under restricted-only policy | Policy not applicable |
| Duplicate resource identifier | Registration rejected |
| Missing resource identifier | Validation failure |
| Unknown resource lookup | Resource-not-found exception |
| Unauthorized remediation | Authorization failure |
| Approved remediation | Resource configuration updated |
| Resource reassessment | New compliance result recorded |
| Modified audit event | Integrity verification fails |
| Missing residency configuration | Residency evaluation rejected |

These scenarios distinguish technical validation, governance policy enforcement, regulatory evaluation and administrative authorization.

---

## 18. Cross-Language Engineering Comparison

| Engineering aspect | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Main perspective | Workflow simulation | Event-driven governance | Explicit governance engine | Enterprise domain model | Persistent relational governance |
| Resource modeling | Dataclasses | Classes | Structs | Records | Relational tables |
| Policy modeling | Immutable dataclass | Policy objects | Policy structs | Interfaces and classes | Policy records |
| State management | Dictionaries | Maps | STL maps | Concurrent maps | Transactions |
| Validation | Exceptions | Runtime validation | Custom exceptions | Domain exceptions | Constraints and triggers |
| Audit | SHA-256 | SHA-256 | Demonstration hash | SHA-256 | SHA-256 |
| Reporting | Dictionaries | Objects | Report structure | Immutable record | Views and aggregation |
| Persistence | JSON export | JSON export | In-memory | In-memory | Relational database |

The implementations share a common governance domain but use language-specific design decisions.

The PostgreSQL database provides persistent workflow records. The four application implementations demonstrate different ways to represent and execute governance operations.

---

## 19. Technical Limitations

The implementations are educational governance engines, not direct integrations with cloud-provider control planes.

They do not automatically retrieve live resource configurations from AWS, Microsoft Azure or Google Cloud.

The following production capabilities would require additional integration and operational infrastructure:

- Cloud-provider API discovery
- Continuous configuration monitoring
- Automated infrastructure provisioning
- Actual encryption configuration changes
- IAM policy inspection
- Network security inspection
- Backup restoration verification
- Data classification discovery
- Legal applicability assessment
- Regulatory evidence collection
- Multi-stage approval workflows
- Immutable external audit retention

The sample residency rules are organizational configuration examples, not universal statements of legal data-localization requirements.

The sample compliance percentage measures policy evaluations, not overall organizational compliance.

The C++ audit implementation uses a non-cryptographic demonstration hash and must not be used for production integrity assurance.

The application implementations use in-memory state except for their JSON exports. The PostgreSQL implementation supplies relational persistence and database-level workflow constraints.

A production system must also handle concurrent resource updates, assessment snapshots, stale evidence, policy versioning, authorization boundaries and configuration drift.

These limitations are important because a governance system must distinguish an implemented control, an evaluated control, an approved corrective action and independently verified compliance evidence.
