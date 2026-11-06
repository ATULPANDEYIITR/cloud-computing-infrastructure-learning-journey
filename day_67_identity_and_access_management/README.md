# Identity and Access Management

## 1. Introduction

Identity and Access Management (IAM) is a framework for controlling which identities can access organizational resources, which operations they can perform, and under what conditions access is permitted.

IAM combines identity lifecycle management, authentication-related identity information, authorization, policy evaluation, and access auditing.

The implementations model an enterprise environment in which employees access application resources, security records, deployment reports, production secrets, and financial information.

The central authorization question is:

**Can this identity perform this action on this resource under the current access conditions?**

An authorization decision must consider the identity's status, group memberships, effective roles, permissions, applicable policies, and temporary assignments.

## 2. IAM Domain Model

The implementations use the following domain relationships:

    Organization
        |
        +-- Users
        |     |
        |     +-- Group Memberships
        |     |
        |     +-- Direct Role Assignments
        |
        +-- Groups
        |     |
        |     +-- Group Roles
        |
        +-- Roles
        |     |
        |     +-- Permissions
        |
        +-- Policies
        |     |
        |     +-- User Principals
        |     +-- Group Principals
        |     +-- Conditions
        |
        +-- Protected Resources
        |
        +-- Authorization Decisions
              |
              +-- Audit Records

The entities have distinct responsibilities.

| Entity | Responsibility |
|---|---|
| User | Represents an individual identity |
| Group | Organizes identities with common access requirements |
| Role | Defines a reusable collection of permissions |
| Permission | Identifies an allowed resource-action combination |
| Policy | Defines conditional authorization rules |
| Assignment | Connects an identity to a role |
| Membership | Connects a user to a group |
| Audit record | Preserves an authorization decision |

## 3. Users and Identity Lifecycle

A user represents an identifiable organizational principal.

The implementations maintain:

- Unique user identifiers.
- Email addresses.
- Active or inactive status.
- Group memberships.
- Direct role assignments.
- Department or contextual attributes.

The Python and C++ implementations use active-state checks. Java provides explicit `ACTIVE`, `SUSPENDED`, and `DISABLED` states. JavaScript represents identity status using an active flag.

The PostgreSQL implementation stores status using an enumerated type.

### Identity lifecycle

    Identity Creation
          |
          v
    Group Membership
          |
          v
    Role Assignment
          |
          v
    Authorization
          |
          v
    Suspension / Deactivation
          |
          v
    Access Denial

An inactive identity cannot obtain access through an otherwise valid role or policy grant.

Suspension and deactivation are important because removing one role does not necessarily remove permissions inherited through another group or assignment.

A production IAM system should also address:

- Employee onboarding.
- Department transfers.
- Employee termination.
- Account recovery.
- Identity verification.
- Service accounts.
- Dormant-account detection.
- Session invalidation.
- Credential rotation.

The supplied implementations simulate identity state and authorization rather than providing password authentication or session management.

## 4. Groups and Membership Management

Groups organize users according to organizational responsibilities.

Examples include:

| Group | Typical responsibility |
|---|---|
| Developers | Application development |
| SecurityTeam | Security monitoring and auditing |
| FinanceTeam | Financial reporting |
| Administrators | Controlled infrastructure administration |

A user can belong to multiple groups.

Group membership allows access requirements to be managed collectively rather than assigning identical roles separately to every employee.

For example:

- Alice belongs to Developers.
- Bob belongs to SecurityTeam.
- Carol belongs to FinanceTeam.

The Developer role can be assigned to Developers once. Every active member then inherits the role's permissions.

Removing a user's group membership removes permissions obtained exclusively through that group.

A user may still retain access through another group or direct assignment. Therefore, membership removal must be evaluated against all remaining authorization sources.

## 5. Roles and Role-Based Access Control

Role-Based Access Control (RBAC) associates permissions with roles and assigns those roles to users or groups.

The relationship is:

    User
      |
      v
    Group Membership
      |
      v
    Group Role
      |
      v
    Role
      |
      v
    Permissions
      |
      v
    Protected Resource

A role is a reusable access profile.

### Implemented roles

| Role | Permissions |
|---|---|
| Developer | Read and write project A |
| SecurityAuditor | Read security logs and reports |
| FinanceAnalyst | Read financial reports |
| IncidentAdministrator | Broad permissions for controlled incident response |

The Administrator role is deliberately treated as a privileged role. Its assignment must be temporary, justified, monitored, and revocable.

### Direct and inherited role assignments

There are two assignment mechanisms:

1. Direct assignment connects a user directly to a role.
2. Group assignment connects a role to a group, allowing members to inherit it.

The effective-role calculation combines both sources.

Duplicate assignments are rejected where the implementation maintains assignment identity.

The PostgreSQL `effective_roles` view combines group-derived and direct roles using `UNION`.

### Effective role calculation

For an active user:

\[
R_{\text{effective}}(u,t)
=
R_{\text{groups}}(u)
\cup
R_{\text{direct}}(u,t)
\]

Where:

- \(u\) represents a user.
- \(t\) represents the evaluation time.
- \(R_{\text{groups}}\) represents roles inherited through group membership.
- \(R_{\text{direct}}\) represents valid direct assignments.

Expired and revoked assignments are excluded.

## 6. Permissions and Resource-Level Authorization

A permission represents an action on a resource.

Its structure is:

    Permission = (Resource, Action)

Examples:

| Resource | Action |
|---|---|
| applications/project-a | read |
| applications/project-a | write |
| applications/project-a | delete |
| security/logs | read |
| production/secrets | read |
| finance/reports | read |

The implementations support exact resource matching, wildcard resources, and resource-prefix matching.

Examples:

| Permission pattern | Request | Result |
|---|---|---|
| `applications/project-a` | `applications/project-a` | Match |
| `applications/*` | `applications/project-a` | Match |
| `applications/*` | `applications/project-b` | Match |
| `security/logs` | `security/reports` | No match |
| `*` | Any resource | Match |

Actions support exact matching and the wildcard `*`.

A wildcard permission grants broad access. It should be restricted to carefully controlled roles and policies.

Resource patterns must be validated. In particular, path traversal sequences such as `..` should not be accepted.

## 7. Policy-Based Access Control

A policy describes an authorization rule.

Each policy includes:

- Policy identifier.
- Name.
- Effect.
- Resource-action permission.
- Applicable users or groups.
- Optional conditions.
- Activation status.
- Optional expiration.

The implementations support two policy effects.

| Effect | Meaning |
|---|---|
| ALLOW | Grants matching access |
| DENY | Explicitly rejects matching access |

### Principal matching

A policy can apply to:

- Specific users.
- Members of specified groups.
- Both categories.

A policy without a principal is rejected.

### Attribute-based conditions

The JavaScript, Java, and PostgreSQL implementations demonstrate contextual conditions.

For example, Alice may read deployment reports only when the request context contains:

    department = Engineering

A request with `department = Finance` does not satisfy this condition.

A condition is not an independent permission grant. The policy must still match the principal, resource, and action.

### Policy evaluation

The authorization engine evaluates:

1. Policy activation.
2. Policy expiration.
3. Principal membership.
4. Resource matching.
5. Action matching.
6. Contextual conditions.
7. Policy effect.

The implementations use explicit deny precedence.

The decision rule is:

\[
D =
\begin{cases}
DENY & \text{if an applicable DENY exists}\\
ALLOW & \text{if a matching grant exists}\\
DENY & \text{otherwise}
\end{cases}
\]

This means that an administrator role does not automatically override an applicable explicit deny policy in these implementations.

This is a deliberately selected authorization model. Other systems may use different policy-combination algorithms, so integration with an external IAM platform requires matching its documented semantics.

## 8. Least Privilege

The principle of least privilege requires each identity to receive only the permissions necessary to perform its assigned responsibilities.

It reduces the potential impact of:

- Compromised credentials.
- Insider misuse.
- Unintended data disclosure.
- Accidental deletion.
- Privilege escalation.
- Unauthorized administrative activity.

### Least-privilege example

A developer requires:

- Read access to project A.
- Write access to project A.

The developer does not automatically require:

- Production secret access.
- Security administration.
- Financial records.
- Global deletion permissions.

The implementation separates these capabilities into different roles and policies.

### Access review

A least-privilege review compares the permissions an identity needs with the permissions currently available.

The Python `audit_user` method, JavaScript `auditUser` method, and PostgreSQL access-report queries evaluate representative resource-action requests.

The C++ implementation evaluates a defined collection of access requests.

An audit distinguishes:

- Expected access.
- Granted access.
- Denied access.
- Unused assignments.
- Excessive privileges.
- Inherited permissions.

A denied request is not necessarily evidence of a security incident. It may represent correct enforcement of the authorization model.

### Privilege reduction

A practical review process is:

    Identify Identity
          |
          v
    Retrieve Effective Roles
          |
          v
    Expand Effective Permissions
          |
          v
    Compare With Job Requirements
          |
          v
    Identify Excessive Access
          |
          v
    Revoke Unnecessary Assignments
          |
          v
    Re-evaluate Authorization

Least privilege is a continuous governance process, not a one-time configuration.

## 9. Temporary Privilege Elevation

Temporary privilege elevation provides additional permissions for a limited period.

The implementations demonstrate temporary role assignments with expiration timestamps.

For example, a security engineer may receive the IncidentAdministrator role for 30 minutes to investigate a production incident.

An assignment is valid when:

\[
t_{\text{current}} < t_{\text{expiry}}
\]

An expired assignment must not contribute to effective permissions.

The Python implementation uses timezone-aware `datetime` objects.

JavaScript uses `Date` objects.

C++ uses `std::chrono`.

Java uses `Instant`.

PostgreSQL uses `TIMESTAMPTZ`.

### Revocation

Revocation must immediately remove the assignment from subsequent authorization evaluations.

The Python, JavaScript, C++, and Java implementations remove or invalidate assignment records.

PostgreSQL preserves assignment history using `revoked_at`.

Preserving historical assignment information supports security investigations and administrative accountability.

Production implementations should also require:

- Approval for privileged access.
- Justification records.
- Strong authentication.
- Short expiration periods.
- Administrative notifications.
- Immutable audit records.

## 10. Authorization Workflow

The implemented authorization workflow follows this sequence:

    Access Request
          |
          v
    Validate Request
          |
          v
    Retrieve Identity
          |
          v
    Check Identity Status
          |
          v
    Resolve Group Membership
          |
          v
    Calculate Effective Roles
          |
          v
    Evaluate Role Permissions
          |
          v
    Evaluate Applicable Policies
          |
          v
    Apply Explicit Deny Precedence
          |
          v
    ALLOW or DENY
          |
          v
    Record Audit Event

### Authorization inputs

An authorization request contains:

| Input | Purpose |
|---|---|
| User ID | Identifies the requesting principal |
| Resource | Identifies the protected object |
| Action | Identifies the requested operation |
| Context | Supplies relevant request attributes |
| Evaluation time | Determines whether temporary grants and policies remain valid |

### Failure conditions

The implementations handle several failure states:

- Unknown user.
- Unknown group.
- Unknown role.
- Duplicate identity.
- Duplicate membership.
- Invalid permission.
- Invalid policy effect.
- Missing policy principal.
- Expired role assignment.
- Inactive user.
- Explicit deny.
- No matching grant.

Invalid configuration raises an exception rather than silently granting access.

## 11. Python Implementation

The Python program uses object-oriented domain modeling and standard-library features.

### Main components

| Component | Responsibility |
|---|---|
| `User` | Identity information |
| `Group` | Group membership and role relationships |
| `Role` | Permission collection |
| `Permission` | Resource-action matching |
| `Policy` | Conditional authorization rule |
| `RoleAssignment` | Direct and temporary role assignment |
| `IAM` | Central IAM service |
| `AccessResult` | Structured authorization result |

### Implementation decisions

The program uses:

- Dataclasses for domain records.
- Enums for policy effects and decisions.
- Dictionaries for indexed entity lookup.
- Sets for unique memberships and permissions.
- Lists for assignment history.
- Exceptions for invalid operations.
- JSON for configuration persistence.
- Assertions for functional verification.

The `evaluate` method performs the central authorization calculation.

The `effective_roles` method resolves group-derived and direct roles.

The `audit_user` method performs least-privilege access checks.

The `save` and `load` methods demonstrate configuration persistence.

The configuration loader validates references after reconstructing entities. JSON persistence is intended for a learning simulation, not a production-grade transactional identity database.

### Execution

Run the program using Python 3:

    python iam.py

The program prints access decisions, a least-privilege report, persistence verification, and assertion results.

## 12. JavaScript Implementation

The JavaScript implementation uses an event-driven architecture.

### Main components

| Component | Responsibility |
|---|---|
| `IdentityStore` | Maintains IAM entities |
| `Map` | Stores users, groups, roles, and policies |
| `Set` | Tracks memberships and role relationships |
| `EventEmitter` | Publishes identity and assignment events |
| `authorize` | Provides asynchronous authorization |
| `evaluate` | Calculates access decisions |
| `auditUser` | Evaluates a collection of permissions |

### Event-driven behavior

The system emits events for:

- User creation.
- Group creation.
- Membership changes.
- Role creation.
- Role assignment.
- Role revocation.
- User deactivation.
- Access decisions.

These events separate state changes from their consumers.

For example, a monitoring component can listen for access-decision events without modifying the authorization engine.

The implementation uses `crypto.randomUUID()` to generate request and assignment identifiers.

The asynchronous `authorize` method demonstrates an authorization boundary suitable for integration with an asynchronous service architecture.

The implementation uses in-memory storage. Event listeners and in-memory audit records do not provide durable delivery or tamper-resistant audit storage.

### Execution

Run using Node.js:

    node iam.js

No third-party npm package is required.

## 13. C++17 Implementation

The C++ implementation focuses on an explicit authorization engine using strongly structured domain records.

### Main components

| Component | Responsibility |
|---|---|
| `IAMEngine` | Authorization and identity management |
| `User` | Identity state |
| `Group` | Group-to-role relationships |
| `Role` | Permission collection |
| `Policy` | Explicit authorization rules |
| `Assignment` | Time-limited role assignment |
| `AccessRequest` | Authorization input |
| `AccessResult` | Authorization output |

### Data structures

The program uses:

- `std::map` for entity lookup.
- `std::set` for unique role and membership relationships.
- `std::vector` for assignments and permissions.
- `std::optional` for optional expiration timestamps.
- STL algorithms for permission matching and assignment revocation.
- `std::chrono` for time-based authorization.

The ordered maps provide predictable logarithmic lookup complexity.

The use of sets prevents duplicate memberships and role relationships.

The implementation explicitly separates role-derived grants from policy-derived grants before applying deny precedence.

### Complexity considerations

Let:

- \(U\) represent the number of users.
- \(G\) represent the number of groups.
- \(R\) represent the number of roles.
- \(P\) represent the number of policies.
- \(A\) represent the number of direct assignments.

Typical operations include:

| Operation | Approximate complexity |
|---|---|
| User lookup | \(O(\log U)\) |
| Group lookup | \(O(\log G)\) |
| Role lookup | \(O(\log R)\) |
| Membership insertion | \(O(\log G)\) |
| Effective-role resolution | Depends on memberships and assignments |
| Policy evaluation | Depends on applicable policies and their permissions |

The current implementation scans assignments and policies during authorization. A production engine could use indexed assignments, cached effective roles, and indexed policy retrieval.

### Compilation

Compile with a C++17 compiler:

    g++ -std=c++17 -O2 -Wall -Wextra -pedantic iam.cpp -o iam

Run:

    ./iam

## 14. Java 17 Enterprise Implementation

The Java implementation emphasizes explicit domain types, encapsulated state, and service-layer authorization.

### Domain architecture

| Component | Responsibility |
|---|---|
| `User` | Identity lifecycle |
| `Group` | Group membership |
| `Role` | Permission definition |
| `Permission` | Resource-action matching |
| `Policy` | Conditional authorization |
| `RoleAssignment` | Temporary privilege management |
| `IAMService` | Identity and authorization operations |
| `AuditService` | Decision reporting |
| `AuthorizationService` | Authorization interface |

### Java 17 features

The implementation uses:

- Records for immutable request and result objects.
- Enums for status and decision types.
- Interfaces for authorization service boundaries.
- Collections for entity management.
- Streams for condition and permission evaluation.
- Generics through Java collection types.
- `Instant` for timestamp management.
- `UUID` for request identifiers.
- Custom exceptions for operational failures.

### State transitions

User states are represented by:

| State | Meaning |
|---|---|
| ACTIVE | Authorization can proceed |
| SUSPENDED | Authorization is denied |
| DISABLED | Authorization is denied |

The status transition is separate from role assignment.

Changing an identity's status does not require deleting its roles or historical assignments.

This preserves administrative history while ensuring that inactive identities cannot use those grants.

### Service separation

`IAMService` handles identity relationships and authorization.

`AuditService` records decisions and produces aggregate counts.

The `AuthorizationService` interface defines the authorization boundary independently of its implementation.

This separation makes it possible to replace an in-memory authorization engine with a database-backed or remote authorization service.

### Compilation

Compile using Java 17:

    javac --release 17 IAMEnterprise.java

Run:

    java IAMEnterprise

## 15. PostgreSQL Relational Implementation

The PostgreSQL script provides a normalized relational model for enterprise IAM.

It creates the `iam` schema and separates identities, memberships, roles, permissions, assignments, policies, and audit records.

### Relational structure

| Table | Purpose |
|---|---|
| `users` | Identity records |
| `groups` | Organizational groups |
| `user_groups` | Many-to-many membership |
| `roles` | Reusable role definitions |
| `permissions` | Resource-action definitions |
| `role_permissions` | Role-to-permission mapping |
| `group_roles` | Group-to-role mapping |
| `role_assignments` | Direct user role assignments |
| `policies` | Policy definitions |
| `policy_users` | User policy principals |
| `policy_groups` | Group policy principals |
| `policy_conditions` | Contextual policy conditions |
| `access_audit` | Authorization decisions |
| `security_events` | Security-related administrative events |

### Many-to-many relationships

Users and groups have a many-to-many relationship.

A user can join several groups, and a group can contain several users.

Roles and permissions also have a many-to-many relationship.

A role can contain several permissions, while a permission can be reused by multiple roles.

The mapping tables use composite primary keys to prevent duplicate relationships.

### Integrity enforcement

The database uses:

- Primary keys.
- Foreign keys.
- Unique constraints.
- Check constraints.
- Enumerated types.
- Partial indexes.
- Triggers.
- Stored functions.
- Stored procedures.

The system-role deletion trigger prevents deletion of predefined system roles.

The deferred policy-principal constraint trigger validates that a policy has at least one user or group principal at transaction completion.

The deferred trigger allows a policy and its principal mappings to be inserted in the same transaction.

### Effective roles and permissions

The `effective_roles` view combines direct and group-derived role assignments.

The `effective_permissions` view expands effective roles into their permissions.

These views provide reusable relational access paths for retrieval and reporting.

### Authorization function

The `iam.evaluate_access` function is the central database authorization mechanism.

It:

1. Validates the request.
2. Retrieves the identity status.
3. Resolves effective roles.
4. Evaluates role permissions.
5. Finds applicable user and group policies.
6. Evaluates policy expiration.
7. Checks contextual attributes.
8. Applies explicit deny precedence.
9. Records the decision.
10. Returns the decision and matching identifiers.

### Access enforcement procedure

`iam.require_access` calls the authorization function.

If access is denied, it raises PostgreSQL SQLSTATE `42501`, representing insufficient privilege.

This separates authorization evaluation from the operation that requires authorization.

A production application must ensure that protected data operations are executed within a controlled transaction and that application users cannot bypass the enforcement layer through direct table access.

### Revocation procedure

`iam.revoke_role` marks an assignment as revoked instead of deleting its historical record.

This preserves the assignment lifecycle for auditing.

### Transaction handling

The script uses a transaction around schema creation, sample data, evaluations, and revocation.

The revocation demonstration uses a savepoint.

If an operation fails, the surrounding transaction can be rolled back rather than leaving partially applied changes.

### Performance considerations

Indexes support common authorization access patterns:

- User-to-group membership.
- Group-to-role lookup.
- User-to-role assignment.
- Active assignment filtering.
- User-specific policy lookup.
- Group-specific policy lookup.
- User audit history.
- Time-based security event retrieval.

The partial index on non-revoked assignments reduces the indexed data relevant to active assignment queries.

The script includes an `EXPLAIN` example to inspect a representative assignment lookup plan.

## 16. Distinction Between Authentication and Authorization

Authentication and authorization solve different security problems.

| Authentication | Authorization |
|---|---|
| Verifies identity | Determines permitted operations |
| Validates credentials or authentication factors | Evaluates roles, permissions, and policies |
| Establishes an authenticated principal | Determines resource access |
| May use passwords, certificates, or MFA | Uses access-control rules |

The implementations focus on authorization and identity-state management.

They do not implement password verification, multifactor authentication, identity federation, token issuance, or session management.

A production IAM platform must integrate these capabilities where required.

## 17. Security Considerations

### Explicit deny precedence

The implementations deny a request when an applicable explicit deny policy matches, even when a role or another policy grants access.

### Inactive identities

Suspended, disabled, or deactivated users cannot obtain access through existing assignments.

### Temporary assignments

Expiration limits the lifetime of elevated permissions.

### Wildcard permissions

Wildcard permissions must be restricted because they can grant access across multiple resource categories.

### Policy conditions

Contextual attributes must be derived from trusted sources.

A client must not be allowed to freely assert sensitive authorization attributes such as department, clearance, or approval status.

### Audit integrity

Authorization decisions should be recorded with sufficient context to support investigation.

A production audit system should consider:

- Append-only storage.
- Restricted audit modification privileges.
- Timestamp synchronization.
- Retention requirements.
- Correlation identifiers.
- Security event monitoring.
- Sensitive-data minimization.

### Privilege escalation

A user must not be able to assign privileged roles to themselves or modify policies that govern their own access without independent authorization.

The learning implementations validate entity references but do not implement a complete administrative approval hierarchy.

## 18. Limitations and Production Considerations

The five implementations demonstrate core IAM behavior rather than complete enterprise identity platforms.

| Area | Implemented behavior | Production consideration |
|---|---|---|
| Identity | User creation and status | Federation and lifecycle provisioning |
| Groups | Membership management | Nested groups and synchronization |
| Roles | Direct and inherited assignments | Role hierarchy governance |
| Permissions | Resource-action matching | Resource ownership and tenant isolation |
| Policies | Allow, deny, and selected conditions | Complete policy language and conflict semantics |
| Temporary access | Expiration and revocation | Approval and privileged-access monitoring |
| Auditing | Authorization decision records | Tamper-resistant centralized storage |
| Persistence | JSON or relational records | Durable storage and concurrency control |
| Performance | Indexed entities and database queries | Caching and distributed authorization |
| Authentication | Not implemented | MFA, credentials, and identity federation |

The in-memory implementations are single-process demonstrations. They do not provide distributed consistency, concurrent transaction isolation, or durable audit guarantees.

The PostgreSQL script provides relational persistence, but database privileges, row-level security, connection security, operational backup, and application-level transaction boundaries must still be configured for a deployed environment.

The policy model is intentionally limited to the resource, action, principal, expiration, and selected contextual conditions demonstrated in the source files.

The examples also use broad administrative permissions to illustrate privilege risk. Real administrative access should be divided into narrower responsibilities and subject to independent governance.
