# Cloud Security Fundamentals

## 1. Domain Overview

Cloud security is the protection of cloud-hosted infrastructure, applications, identities, networks, workloads, and data against unauthorized access, misuse, disruption, and compromise.

Unlike traditional infrastructure, cloud environments operate through provider-managed services, programmable infrastructure, distributed identities, APIs, and dynamically created resources.

Cloud security therefore requires two complementary capabilities:

- Understanding which security responsibilities belong to the cloud provider and which remain with the customer.
- Continuously identifying and controlling risks across the cloud environment.

This project implements a cloud security assessment system across Python, JavaScript, C++17, Java 17, and PostgreSQL.

The implementations examine:

- Shared responsibility.
- Cloud service models.
- Cloud attack surfaces.
- Cloud threat categories.
- Identity and access management.
- Network security.
- Data protection.
- Security monitoring.
- Risk assessment.
- Security remediation.

## 2. Cloud Computing Security Architecture

A cloud environment consists of interconnected resources managed through provider APIs and customer configurations.

A simplified architecture is:

    Cloud Provider
        |
        +-- Physical Infrastructure
        |
        +-- Virtualization Layer
        |
        +-- Managed Cloud Services
        |
        +-- Customer Cloud Account
                |
                +-- Compute Resources
                +-- Storage Resources
                +-- Databases
                +-- Network Resources
                +-- Identities and Roles
                +-- Applications
                +-- Customer Data
                |
                +-- Security Controls
                        |
                        +-- IAM
                        +-- Encryption
                        +-- Network Restrictions
                        +-- Logging
                        +-- Backup
                        +-- Monitoring

The security of a cloud deployment depends on both provider controls and customer configuration.

A secure physical infrastructure does not automatically produce a secure cloud application. An improperly configured storage resource, exposed database, or compromised identity can create significant security risks even when the underlying provider infrastructure is functioning correctly.

## 3. Shared Responsibility Model

The shared responsibility model defines the division of security responsibilities between a cloud service provider and its customer.

The provider protects the cloud infrastructure. The customer protects their resources, identities, data, and configurations according to the selected service.

The exact division depends on the cloud provider, service model, and individual managed service.

### 3.1 Infrastructure as a Service

IaaS provides virtualized computing resources such as virtual machines, networks, and storage.

The provider generally manages:

- Physical facilities.
- Physical hardware.
- Physical networking.
- Virtualization infrastructure.

The customer generally manages:

- Guest operating systems.
- Application software.
- Data.
- Identity permissions.
- Firewall and network configurations.
- Operating system patching.

### 3.2 Platform as a Service

PaaS provides managed application platforms and execution environments.

The provider generally manages:

- Physical infrastructure.
- Virtualization.
- Managed operating systems.
- Runtime infrastructure.
- Platform maintenance.

The customer generally manages:

- Application code.
- Application configuration.
- Data.
- User identities.
- Application-level permissions.

### 3.3 Software as a Service

SaaS provides complete applications through a cloud service.

The provider generally manages:

- Physical infrastructure.
- Operating systems.
- Application infrastructure.
- Application maintenance.
- Platform availability.

The customer remains responsible for:

- Data classification.
- User access.
- Identity security.
- Account configuration.
- Secure usage.
- Appropriate retention and sharing policies.

### 3.4 Responsibility Comparison

| Security responsibility | IaaS | PaaS | SaaS |
|---|---|---|---|
| Physical infrastructure | Provider | Provider | Provider |
| Hypervisor | Provider | Provider | Provider |
| Guest operating system | Customer | Generally provider | Provider |
| Managed runtime | Customer-managed | Provider-managed | Provider-managed |
| Application | Customer | Customer | Generally provider |
| Data classification | Customer | Customer | Customer |
| Identity configuration | Customer | Customer | Customer |
| Network configuration | Customer | Shared/service-dependent | Shared/service-dependent |
| Security monitoring | Shared | Shared | Shared |

The table represents a general service-model distinction. Actual responsibility assignments must be verified against the individual service contract and provider documentation.

### 3.5 Implementation

The Python implementation defines `SharedResponsibilityModel`.

The JavaScript implementation uses `ResponsibilityEngine`.

The C++ implementation uses `ResponsibilityModel`.

The Java implementation uses `ResponsibilityRegistry` and `ServiceModelPolicy`.

The PostgreSQL implementation stores responsibility assignments in:

- `security_controls`
- `service_models`
- `service_responsibilities`

The relational design separates security controls from service-specific ownership. This prevents the mistaken assumption that all controls have identical ownership across every service model.

## 4. Cloud Attack Surface

An attack surface is the collection of entry points, interfaces, resources, identities, and configurations that an attacker could potentially exploit.

Cloud attack surfaces are dynamic because resources can be created, modified, exposed, and removed through APIs and automated deployment systems.

### 4.1 Infrastructure Attack Surface

Infrastructure-related exposure includes:

- Public virtual machines.
- Open management ports.
- Unrestricted security groups.
- Public database endpoints.
- Exposed administrative interfaces.
- Insecure network routes.

An exposed resource is not automatically compromised. Exposure increases the opportunity for unauthorized access and must be evaluated alongside authentication, authorization, vulnerabilities, and network controls.

### 4.2 Storage Attack Surface

Cloud storage can expose confidential information through:

- Public bucket configurations.
- Incorrect access-control policies.
- Excessive sharing permissions.
- Missing encryption.
- Insecure object access.
- Unprotected backup files.

The implementations identify publicly accessible storage as a critical finding.

### 4.3 Identity Attack Surface

Cloud identities include:

- Human users.
- Administrative accounts.
- Service accounts.
- Application identities.
- Managed identities.
- Roles and temporary credentials.

Identity-related risks include:

- Excessive permissions.
- Unprotected privileged accounts.
- Missing MFA.
- Long-lived credentials.
- Unused accounts.
- Compromised access tokens.

Identity security is particularly important because cloud control-plane APIs can create, modify, and delete infrastructure.

### 4.4 Application Attack Surface

Application exposure includes:

- Public API endpoints.
- Vulnerable dependencies.
- Insecure application configurations.
- Weak authentication.
- Injection vulnerabilities.
- Exposed secrets.
- Insecure application-to-service communication.

### 4.5 Attack Surface Discovery

The implementations classify assets into four important categories:

| Category | Purpose |
|---|---|
| Internet-exposed assets | Identify externally reachable resources |
| Identity assets | Identify identity-related security boundaries |
| Sensitive-data assets | Identify resources containing confidential information |
| Network assets | Identify network boundaries requiring protection |

Python uses dictionaries and sets for assessment.

JavaScript uses structured objects and asynchronous inspection.

C++ uses dedicated attack-surface data structures.

Java uses immutable collections and streams.

PostgreSQL provides the `attack_surface_report` view.

## 5. Cloud Security Threats

A threat is a potential cause of an unwanted security incident.

A vulnerability is a weakness that can be exploited. A threat actor is an entity capable of exploiting weaknesses. Risk combines the likelihood and impact of a security event.

### 5.1 Data Breach

A data breach occurs when confidential information is accessed, disclosed, or acquired without authorization.

Potential causes include:

- Public storage exposure.
- Excessive database permissions.
- Compromised credentials.
- Insecure application interfaces.
- Missing encryption controls.

Important security controls include:

- Encryption at rest.
- Encryption in transit.
- Data classification.
- Least privilege.
- Access monitoring.
- Data-loss prevention.

### 5.2 Account Compromise

Account compromise occurs when an unauthorized person gains control of a cloud identity.

Common attack paths include:

- Credential theft.
- Phishing.
- Password reuse.
- Token theft.
- Missing MFA.
- Exposed access keys.

Defensive controls include:

- MFA.
- Strong authentication.
- Short-lived credentials.
- Conditional access.
- Privileged access management.
- Identity activity monitoring.

### 5.3 Cloud Misconfiguration

Misconfiguration occurs when a cloud resource is deployed or maintained with insecure settings.

Examples include:

- Public storage access.
- Unrestricted network rules.
- Excessive IAM permissions.
- Disabled logging.
- Missing encryption.
- Inadequate backup configuration.

Misconfiguration is especially important because many cloud resources are configured through APIs, templates, deployment pipelines, and management consoles.

### 5.4 Denial of Service

Denial of Service attacks attempt to reduce or eliminate service availability.

Potential consequences include:

- Resource exhaustion.
- Increased infrastructure costs.
- Application unavailability.
- Database overload.
- Network congestion.

Relevant defensive mechanisms include rate limiting, traffic filtering, capacity management, service quotas, and distributed denial-of-service protection.

### 5.5 Malware

Malware can compromise cloud-hosted virtual machines, containers, serverless workloads, and application environments.

Possible consequences include:

- Unauthorized access.
- Data theft.
- Resource abuse.
- Lateral movement.
- Destructive activity.

Defensive mechanisms include workload protection, vulnerability management, application controls, monitoring, and isolation.

### 5.6 Insider Threat

An insider threat originates from an individual or identity with legitimate access.

Examples include:

- Unauthorized data extraction.
- Privilege misuse.
- Unauthorized configuration changes.
- Destructive administrative activity.

Controls include separation of duties, access reviews, activity logging, and privileged account monitoring.

### 5.7 Supply Chain Compromise

A supply chain compromise involves a trusted dependency, vendor, package, image, or external service.

Cloud workloads can inherit vulnerabilities from:

- Container images.
- Software libraries.
- Build systems.
- Deployment pipelines.
- Third-party integrations.

Relevant controls include dependency verification, image scanning, signed artifacts, access restrictions, and deployment integrity checks.

## 6. Core Cloud Security Principles

### 6.1 Least Privilege

Least privilege means providing an identity only the permissions required to perform its assigned function.

For example:

| Identity | Required permission |
|---|---|
| Reporting application | Read reporting data |
| Backup service | Read source data and write backups |
| Application administrator | Manage approved application resources |
| Monitoring service | Read approved monitoring information |

An identity with unrestricted wildcard permissions has a larger potential impact if compromised.

The implementations detect wildcard permissions and explicitly identify excessive IAM access.

### 6.2 Zero Trust

Zero Trust is a security approach based on the principle that access should not be trusted merely because a user or workload is inside a network boundary.

Important principles include:

- Verify identities.
- Authenticate access requests.
- Authorize access according to policy.
- Apply least privilege.
- Continuously evaluate security context.
- Monitor access activity.

Network location alone should not establish trust.

### 6.3 Defense in Depth

Defense in Depth uses multiple independent security layers.

A cloud deployment can combine:

1. Identity authentication.
2. Authorization.
3. Network segmentation.
4. Application security.
5. Data encryption.
6. Logging and monitoring.
7. Backup and recovery.

If one control fails, other controls may reduce the impact of the incident.

### 6.4 Secure by Default

Secure-by-default configurations minimize unnecessary exposure.

Examples include:

- Private storage by default.
- Restricted inbound network access.
- Encryption enabled by default.
- MFA for privileged identities.
- Protected audit logs.
- Explicit permission assignments.

### 6.5 Continuous Monitoring

Cloud security cannot rely only on an initial assessment.

Resources and permissions change over time. Continuous monitoring identifies newly introduced risks and verifies that previously corrected problems have not returned.

## 7. Identity and Access Management

Identity and Access Management controls who can access cloud resources and which operations they can perform.

IAM commonly involves:

- Authentication.
- Authorization.
- Users.
- Groups.
- Roles.
- Policies.
- Service identities.
- Temporary credentials.

### 7.1 Authentication

Authentication verifies an identity.

Examples include:

- Password-based authentication.
- Multi-factor authentication.
- Certificates.
- Federated identity.
- Workload identity.

### 7.2 Authorization

Authorization determines which actions an authenticated identity can perform.

An authorization decision can depend on:

- Identity.
- Requested action.
- Target resource.
- Resource attributes.
- Policy conditions.
- Environmental context.

### 7.3 Least-Privilege Evaluation

The implementations detect:

- Explicit wildcard permissions.
- Policies that violate least-privilege configuration.
- Missing MFA.

The PostgreSQL implementation records individual permissions in `iam_permissions`.

A wildcard permission is not automatically equivalent to a specific privilege in every provider's authorization engine. The assessment therefore treats wildcard permissions as a warning requiring policy review rather than attempting to reproduce every provider-specific IAM evaluation rule.

## 8. Network Security

Cloud network security controls communication between workloads, users, and external systems.

Important mechanisms include:

| Mechanism | Purpose |
|---|---|
| Virtual networks | Isolate cloud workloads |
| Subnets | Divide network environments |
| Security groups | Control resource-level traffic |
| Network ACLs | Control subnet-level traffic |
| Firewalls | Filter network communication |
| Private endpoints | Reduce public network exposure |
| Network segmentation | Limit lateral movement |
| TLS | Protect data in transit |

### 8.1 Network Segmentation

Segmentation separates workloads according to function and security requirements.

For example:

    Internet
       |
       v
    Public Load Balancer
       |
       v
    Application Subnet
       |
       v
    Private Database Subnet
       |
       v
    Protected Data Storage

The database should not need unrestricted public exposure to serve an application.

### 8.2 Attack Path Reduction

Network restrictions reduce the number of possible paths through which an attacker can reach sensitive resources.

The implementations identify assets where network restrictions are disabled.

This is a configuration assessment, not a full network reachability or packet-level analysis.

## 9. Data Protection and Encryption

Cloud data protection requires controls throughout the information lifecycle.

### 9.1 Encryption at Rest

Encryption at rest protects stored information.

Common targets include:

- Object storage.
- Database storage.
- Virtual machine disks.
- Backup archives.
- Snapshots.

Encryption can use provider-managed or customer-managed keys.

### 9.2 Encryption in Transit

Encryption in transit protects communication between endpoints.

TLS is widely used for securing application and API communication.

A secure deployment should reject insecure transport configurations where sensitive communication is involved.

### 9.3 Key Management

Encryption depends on the secure management of cryptographic keys.

Key management includes:

- Key generation.
- Key storage.
- Access restrictions.
- Rotation.
- Revocation.
- Audit logging.
- Recovery procedures.

A correctly encrypted resource can still be exposed if unauthorized identities can access its encryption keys.

### 9.4 Backup Protection

Backups support recovery from:

- Accidental deletion.
- Hardware failures.
- Ransomware.
- Data corruption.
- Operational mistakes.

Backup security requires encryption, restricted access, retention policies, and tested restoration procedures.

The implementations detect resources without enabled backup protection.

## 10. Security Logging and Monitoring

Security logging records activities relevant to the investigation and detection of security incidents.

Examples include:

- Authentication events.
- Failed access attempts.
- Administrative actions.
- Permission changes.
- Network events.
- Resource creation and deletion.
- Configuration modifications.

### 10.1 Centralized Logging

Centralized logging consolidates security events from multiple resources and accounts.

Its advantages include:

- Cross-resource investigation.
- Centralized alerting.
- Incident correlation.
- Historical analysis.
- Audit support.

Logs should be protected against unauthorized alteration and deletion.

### 10.2 Monitoring

Monitoring examines security events and resource behavior to identify suspicious activity.

Examples include:

- Unusual authentication patterns.
- Unexpected privilege escalation.
- Abnormal API activity.
- Unexpected data transfers.
- Changes to security configurations.

The Python, JavaScript, C++, and Java implementations detect disabled logging.

The implementations do not perform real-time log ingestion or anomaly detection. Their focus is configuration-level security assessment.

## 11. Risk Assessment and Prioritization

Risk assessment helps determine which security problems should receive attention first.

The implementations use a deterministic rule-based scoring system.

| Finding | Risk score | Severity |
|---|---:|---|
| Public storage | 40 | Critical |
| Public database | 40 | Critical |
| Unencrypted sensitive data | 35 | Critical |
| Excessive IAM permissions | 25 | High |
| Missing MFA | 25 | High |
| Missing TLS enforcement | 25 | High |
| Disabled logging | 20 | High |
| Unrestricted network | 20 | High |
| Disabled backup | 15 | Medium |

These are educational prioritization weights, not calibrated probabilities or universally applicable risk measurements.

### 11.1 Risk Interpretation

A risk assessment should consider:

- Asset criticality.
- Data sensitivity.
- Exposure.
- Threat likelihood.
- Exploitability.
- Potential impact.
- Existing compensating controls.

A public database containing confidential production data can deserve greater attention than an isolated development resource.

### 11.2 Risk-Based Workflow

    Cloud Asset Discovery
            |
            v
    Security Configuration Assessment
            |
            v
    Threat and Vulnerability Identification
            |
            v
    Severity Classification
            |
            v
    Risk Prioritization
            |
            v
    Remediation
            |
            v
    Reassessment

The implementations sort findings by descending risk score to support prioritization.

## 12. Python Implementation

**File:** `cloud_security.py`

The Python implementation provides a complete cloud security assessment workflow using standard-library features.

### 12.1 Domain Modeling

The `CloudAsset` dataclass represents an individual cloud resource.

It stores:

- Asset identifier.
- Cloud provider.
- Asset type.
- Region.
- Internet exposure.
- Encryption configuration.
- Logging configuration.
- MFA configuration.
- IAM permissions.
- Network restrictions.
- Backup status.

Enums constrain the supported provider, asset, severity, and responsibility values.

### 12.2 Shared Responsibility

`SharedResponsibilityModel` maintains a dictionary of security controls and their assigned owners.

The lookup operation rejects unknown controls instead of silently assigning an incorrect responsibility.

### 12.3 Security Scanner

`CloudSecurityScanner` performs deterministic configuration checks.

Each detected violation becomes a `SecurityFinding`.

Findings contain:

- Asset identifier.
- Rule identifier.
- Severity.
- Description.
- Remediation.
- Responsibility.
- Risk score.

The scanner uses a set to identify duplicate asset identifiers.

### 12.4 Reporting

The implementation provides:

- Finding prioritization.
- Severity aggregation.
- Total risk calculation.
- JSON report generation.

The report is written to `cloud_security_report.json`.

### 12.5 Validation and Failure Handling

The script checks:

- Empty identifiers.
- Invalid regions.
- Invalid permission collections.
- Duplicate assets.
- Inactive resources.
- Unknown responsibility controls.

The `run_tests()` function verifies the primary assessment behavior using assertions.

### 12.6 Complexity

Let:

- A represent the number of cloud assets.
- P represent the average number of permissions per asset.
- F represent the number of detected findings.

The basic configuration scan takes approximately O(A + P) time when permission checks use constant-time membership operations.

Sorting findings takes O(F log F).

Asset inventory validation uses a set, giving expected O(1) duplicate detection per asset.

## 13. JavaScript Implementation

**File:** `cloud_security.js`

The JavaScript implementation provides an event-driven security assessment engine.

Its engineering emphasis is asynchronous execution, event publication, and bounded concurrency.

### 13.1 Event-Driven Architecture

`SecurityEventBus` extends Node.js `EventEmitter`.

When a security finding is detected, the engine publishes:

`security:finding`

Event subscribers can independently process security findings.

Possible consumers include:

- Alerting systems.
- Security dashboards.
- Incident management systems.
- Audit pipelines.

The implementation uses an internal event bus rather than making actual external notifications.

### 13.2 Asynchronous Assessment

`CloudSecurityEngine.scan()` processes cloud assets in batches.

The configured concurrency limit prevents the assessment from initiating an unlimited number of simultaneous inspection operations.

`Promise.all()` executes the checks within each batch.

This architecture is suitable for extending the assessment engine to asynchronous cloud inventory APIs.

### 13.3 Attack Surface Discovery

`discoverAttackSurface()` groups resources into:

- Internet-exposed assets.
- Identity-sensitive assets.
- Sensitive-data assets.
- Network boundary assets.
- Inactive assets.

This produces a structured representation for further security analysis.

### 13.4 Reporting

`generateReport()` generates a report containing:

- Scan identifier.
- Assessment timestamp.
- Asset count.
- Finding count.
- Severity distribution.
- Attack surface.
- Individual findings.

`saveReport()` writes the result to a JSON file.

### 13.5 Failure Handling

The implementation validates asset types, identifiers, permissions, and provider names.

It rejects duplicate identifiers and invalid concurrency settings.

The main function handles unexpected assessment failures through a centralized error handler.

## 14. C++17 Implementation

**File:** `cloud_security.cpp`

The C++ implementation emphasizes explicit domain modeling, efficient inventory management, and deterministic security evaluation.

### 14.1 Domain Structures

The program defines:

- `CloudAsset`
- `SecurityFinding`
- `AttackSurface`

Enumerations represent providers, asset types, severity, and responsibility ownership.

### 14.2 Inventory Management

`CloudSecurityEngine` stores assets in a `std::map`.

The asset identifier acts as the inventory key.

This provides:

- Unique resource identification.
- Efficient lookup.
- Duplicate rejection.
- Ordered asset traversal.

Expected insertion and lookup complexity is O(log A).

### 14.3 Attack Surface Analysis

`AttackSurface` identifies exposed resources, identity assets, sensitive-data assets, and network resources.

Vectors store the discovered identifiers.

Inactive assets are excluded from the active attack surface.

### 14.4 Threat Evaluation

The security engine evaluates individual assets using separate rules.

It detects:

- Public storage.
- Public databases.
- Unencrypted sensitive information.
- Excessive permissions.
- Missing MFA.
- Disabled logging.
- Unrestricted network access.
- Missing TLS enforcement.
- Disabled backups.

### 14.5 Finding Prioritization

The STL `sort()` algorithm orders findings by descending risk score.

Asset identifiers provide a deterministic secondary ordering.

### 14.6 Error Handling

The implementation uses exceptions for:

- Invalid assets.
- Duplicate identifiers.
- Unknown security controls.
- Unsupported enum conversions.

The main function catches exceptions and terminates with an appropriate nonzero exit status.

## 15. Java 17 Implementation

**File:** `CloudSecurityFundamentals.java`

The Java implementation models an enterprise-oriented cloud security governance system.

It emphasizes immutable domain objects, explicit policy interfaces, and controlled security finding transitions.

### 15.1 Records and Immutability

The implementation uses Java 17 records for:

- `CloudAsset`
- `SecurityControl`
- `SecurityFinding`

Records reduce unnecessary mutable state.

The asset permission set is copied using `Set.copyOf()`.

This prevents callers from changing the permission collection after asset creation.

### 15.2 Policy Interface

`SecurityPolicy` defines the contract for evaluating a cloud asset.

`CloudSecurityPolicy` implements this contract.

This separates the evaluation mechanism from inventory management and reporting.

Different policy implementations can be introduced without changing the inventory service.

### 15.3 Enterprise Service Architecture

The main components are:

| Component | Responsibility |
|---|---|
| `ResponsibilityRegistry` | Stores responsibility assignments |
| `ServiceModelPolicy` | Evaluates service-model ownership |
| `CloudInventory` | Manages cloud resources |
| `AttackSurfaceAnalyzer` | Identifies exposed resources |
| `CloudSecurityPolicy` | Evaluates security controls |
| `SecurityAssessmentService` | Coordinates assessment and finding lifecycle |

### 15.4 Finding Lifecycle

The implementation defines four finding states:

- OPEN
- IN_PROGRESS
- REMEDIATED
- ACCEPTED

An open finding can move into remediation.

A remediated finding cannot be reopened directly.

An accepted finding requires a new review process.

These restrictions prevent arbitrary status changes and make the workflow more explicit.

### 15.5 Java Streams

Streams are used for:

- Active asset filtering.
- Finding sorting.
- Severity aggregation.
- Risk calculation.

The implementation returns immutable lists from important inventory and assessment operations.

## 16. PostgreSQL Implementation

**File:** `cloud_security.sql`

The PostgreSQL implementation models a relational cloud security assessment and governance workflow.

### 16.1 Database Schema

All domain objects reside in the `cloud_security` schema.

The main tables are:

| Table | Purpose |
|---|---|
| `providers` | Cloud provider registry |
| `service_models` | IaaS, PaaS, and SaaS |
| `security_controls` | Security control definitions |
| `service_responsibilities` | Service-specific ownership |
| `cloud_accounts` | Cloud account inventory |
| `cloud_assets` | Individual cloud resources |
| `cloud_identities` | Cloud identities |
| `iam_permissions` | Identity permission assignments |
| `threats` | Threat classification |
| `security_rules` | Security detection rules |
| `security_findings` | Detected security violations |

### 16.2 Relational Relationships

The primary relationships are:

    Providers
        |
        v
    Cloud Accounts
        |
        +----------------+
        |                |
        v                v
    Cloud Assets    Cloud Identities
        |                |
        |                v
        |          IAM Permissions
        |
        v
    Security Findings
        |
        v
    Security Rules
        |
        v
    Threats

A separate responsibility structure connects service models with security controls.

### 16.3 Constraints

The database uses:

- Primary keys.
- Foreign keys.
- Unique constraints.
- Check constraints.
- Enum types.

Examples include:

- Unique provider names.
- Unique cloud resource references.
- Valid environment classifications.
- Valid permission effects.
- Risk scores between 0 and 100.

These constraints enforce data integrity independently of application logic.

### 16.4 Indexing

The database defines indexes for:

- Account-based asset retrieval.
- Asset type and active status.
- Publicly exposed assets.
- Sensitive resources.
- IAM identity lookup.
- Wildcard permissions.
- Open findings.
- Finding severity.
- Asset-based finding retrieval.

Partial indexes reduce index storage for queries that repeatedly target a specific subset of records.

### 16.5 Assessment Function

`assess_cloud_asset()` evaluates an individual cloud resource.

It checks:

- Public storage exposure.
- Sensitive information without encryption.
- Wildcard IAM permissions.
- Missing MFA.
- Disabled logging.
- Unrestricted network access.
- Missing TLS enforcement.
- Disabled backups.

The function creates findings through SQL inserts.

`ON CONFLICT` prevents duplicate asset-rule findings.

The function uses a row-level lock on the assessed asset to reduce conflicting concurrent assessments of that resource.

### 16.6 Assessment Procedure

`assess_all_cloud_assets()` processes active cloud resources.

It calls the individual assessment function for each resource.

This separates resource-level evaluation from environment-wide assessment.

### 16.7 Triggers and Workflow Integrity

`validate_finding_transition()` prevents direct reopening of remediated findings and direct modification of accepted findings.

The trigger updates the modification timestamp automatically.

This keeps finding lifecycle enforcement inside the database.

### 16.8 Views

Three principal reporting views are provided:

- `attack_surface_report`
- `open_security_findings`
- `cloud_asset_eligibility`

The eligibility view distinguishes:

| Eligibility state | Meaning |
|---|---|
| BLOCKED_CRITICAL_FINDING | At least one unresolved critical finding exists |
| REQUIRES_REMEDIATION | Unresolved findings exist without a critical finding |
| ELIGIBLE | No unresolved findings exist |

This is an educational security eligibility model, not a certification of complete cloud security.

### 16.9 Reporting Queries

The SQL script demonstrates:

- Responsibility retrieval.
- Attack surface retrieval.
- Finding retrieval.
- Severity aggregation.
- Provider-level reporting.
- IAM wildcard detection.
- Risk-based remediation ranking.
- Asset eligibility determination.

The reporting queries use joins, aggregate functions, filtered aggregates, CTEs, and window functions.

### 16.10 Transaction Handling

The SQL script executes schema creation and sample assessment operations inside a transaction.

The remediation example uses a controlled state transition.

The transaction boundary ensures that the initial database setup and sample data operations can be committed together.

## 17. Security Control Mapping

The five implementations use a consistent set of major security controls.

| Security control | Security objective | Primary risk addressed |
|---|---|---|
| IAM least privilege | Limit authorized operations | Account compromise |
| MFA | Strengthen authentication | Credential theft |
| Encryption at rest | Protect stored data | Data disclosure |
| TLS enforcement | Protect data transmission | Interception |
| Network restrictions | Reduce reachable entry points | Unauthorized access |
| Audit logging | Preserve security evidence | Detection failure |
| Backup protection | Support data recovery | Data loss |
| Public access restrictions | Reduce external exposure | Data breach |

These controls are complementary. Implementing one does not remove the need for the others.

## 18. Practical Security Assessment Workflow

The implementations support the following workflow:

### Stage 1: Asset Inventory

Identify cloud providers, accounts, regions, and resource types.

### Stage 2: Responsibility Identification

Determine which controls belong to the provider, customer, or both.

### Stage 3: Attack Surface Discovery

Identify public resources, identity assets, sensitive data, and network boundaries.

### Stage 4: Configuration Assessment

Evaluate access permissions, encryption, MFA, logging, network restrictions, TLS, and backups.

### Stage 5: Threat Identification

Associate configuration weaknesses with relevant cloud threat categories.

### Stage 6: Risk Prioritization

Rank detected findings according to predefined severity and risk scores.

### Stage 7: Remediation

Apply corrective controls and record the finding's workflow state.

### Stage 8: Reassessment

Repeat the security assessment to verify whether identified risks have been addressed.

## 19. Security Limitations and Engineering Trade-offs

The implementations provide a local, rule-based cloud security assessment model.

They do not connect to live AWS, Azure, or GCP environments.

The supplied assets are representative assessment records rather than actual provider resources.

The following limitations are important:

**Provider-specific policy semantics**

AWS IAM, Azure RBAC, and Google Cloud IAM have different authorization models. The implementations identify common permission risks but do not reproduce each provider's complete policy evaluation engine.

**Network reachability**

An internet-exposure flag is a simplified indicator. Actual reachability depends on routing, firewall rules, network interfaces, load balancers, identity controls, and other conditions.

**Encryption**

An encryption-enabled flag does not validate cryptographic algorithms, key strength, key ownership, rotation, or key access permissions.

**MFA**

A Boolean MFA field does not establish whether an authentication mechanism satisfies organizational authentication assurance requirements.

**Logging**

A logging-enabled flag does not verify event completeness, log retention, integrity, alert quality, or centralized collection.

**Risk scoring**

The predefined scores are prioritization weights. They are not statistically calibrated probabilities or a substitute for a formal enterprise risk assessment.

**SQL assessment**

The PostgreSQL assessment uses simplified resource-level checks. Account-wide MFA detection can generate a finding for each assessed resource within an account. A production implementation would normally separate identity-level findings from resource-level findings and use provider-specific policy evaluation.

**Operational deployment**

A production assessment platform requires authenticated provider API access, secure credential management, pagination, rate-limit handling, retry logic, audit trails, and appropriate tenant isolation.

## 20. Cross-Language Implementation Comparison

| Engineering area | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Domain modeling | Dataclasses and enums | Classes and objects | Structs and enums | Records and enums | Relational tables |
| Inventory | Lists and sets | Maps | STL map | LinkedHashMap | Tables |
| Responsibility | Dictionary | Map | Map | Registry | Relational mapping |
| Assessment | Rule-based scanner | Async engine | Evaluation engine | Policy service | SQL function |
| Events | Direct execution | EventEmitter | Direct execution | Service calls | Triggers |
| Reporting | JSON | JSON | Console | Streams | Views and queries |
| Validation | Exceptions | Custom errors | Exceptions | Custom exceptions | Constraints and triggers |
| State management | Finding objects | Engine state | Finding collection | Immutable finding transitions | Finding status |

## 21. Technical Concepts Practiced

The project demonstrates the relationship between cloud security fundamentals and practical software engineering.

| Concept | Implemented mechanism |
|---|---|
| Shared responsibility | Service-specific ownership registry |
| Cloud asset management | Structured inventory |
| Attack surface | Exposure classification |
| Threat detection | Security rule evaluation |
| IAM | Permission inspection |
| Least privilege | Wildcard permission detection |
| Encryption | At-rest and in-transit checks |
| Network security | Network restriction assessment |
| Monitoring | Logging configuration assessment |
| Risk management | Severity and score prioritization |
| Remediation | Finding lifecycle |
| Data integrity | Database constraints |
| Event-driven security | JavaScript event publication |
| Concurrent processing | Bounded asynchronous JavaScript execution |
| Enterprise architecture | Java policy and service classes |
| Efficient lookup | C++ STL and indexed database structures |
| Reporting | JSON, streams, aggregation and SQL views |
