# Authentication and Authorization

## 1. Technical Scope

Authentication and authorization are separate security processes used to control access to applications, APIs, databases, and organizational resources.

Authentication establishes the identity of a user or service. Authorization determines which operations that identity can perform.

This implementation covers seven connected areas:

- Password-based authentication.
- Multi-factor authentication (MFA).
- Access tokens and session management.
- OAuth 2.0 authorization concepts.
- Role-Based Access Control (RBAC).
- Attribute-Based Access Control (ABAC).
- Account security, authorization auditing, and failure handling.

The five implementations use different engineering approaches while maintaining a common identity and access-control model.

| Implementation | Main engineering perspective |
|---|---|
| Python | Integrated identity service and security workflow simulation |
| JavaScript | Asynchronous identity operations and event-driven session management |
| C++17 | Domain-oriented authentication and authorization engine |
| Java 17 | Enterprise identity service and explicit domain modeling |
| PostgreSQL | Relational identity, policy, session, and audit management |

## 2. Authentication and Authorization

### Authentication

Authentication verifies that a presented identity is genuine.

Typical authentication factors include:

| Factor | Description | Example |
|---|---|---|
| Knowledge | Something the user knows | Password or PIN |
| Possession | Something the user controls | Hardware security key or authenticator |
| Inherence | Something the user is | Biometric characteristic |

A password establishes knowledge-based authentication. An authenticator application provides a separate possession-based factor.

A successful password check does not automatically authorize access to every resource.

### Authorization

Authorization evaluates whether an authenticated identity can perform a requested operation.

An authorization decision depends on:

- The authenticated subject.
- The requested action.
- The target resource.
- Assigned roles and permissions.
- Organizational attributes.
- Environmental conditions.
- Applicable security policies.

The general access-control relationship is:

`Subject + Action + Resource + Context -> Authorization Decision`

An authorization decision should default to denial when required information is missing or a policy cannot be evaluated safely.

## 3. Password Security

Passwords are authentication credentials that must be protected against disclosure and offline guessing.

### Password hashing

The Python, JavaScript, and Java implementations demonstrate password hashing through PBKDF2 with HMAC-SHA-256.

The general process is:

1. Generate a cryptographically random salt.
2. Combine the password with the salt.
3. Apply the password-based key derivation function repeatedly.
4. Store the derived hash and its parameters.
5. Recalculate the derived value during authentication.
6. Compare the calculated and stored values using a constant-time comparison operation.

The stored password representation includes:

- Algorithm identifier.
- Iteration count.
- Salt.
- Derived hash.

The salt prevents identical passwords from automatically producing identical stored hashes.

PBKDF2 is a password-based key derivation function. Argon2id is another suitable password-hashing option and is generally preferred for new systems when available and appropriately configured.

### Password validation

The implementations enforce password length and character-class requirements.

The validation rules are educational examples. Real password policies should also consider compromised-password screening, rate limiting, secure recovery, and usability.

Password validation does not replace password hashing.

### Account lockout

The identity services maintain failed authentication counters.

The demonstrated policy is:

| Condition | Result |
|---|---|
| Correct password | Continue authentication |
| Incorrect password | Increment failure counter |
| Five failures | Lock account |
| Locked account | Reject authentication |

Production systems should use distributed rate limiting, progressive delays, monitoring, and recovery procedures. Permanent or easily triggered lockouts can themselves become denial-of-service mechanisms.

## 4. Multi-Factor Authentication

MFA requires more than one independent authentication factor.

The Python, JavaScript, and Java files implement Time-Based One-Time Passwords (TOTP).

### TOTP mechanism

TOTP generates a short-lived numeric code using a shared secret and the current time.

The underlying mechanism uses:

- A shared secret.
- The current Unix timestamp.
- A time-step interval.
- HMAC.
- Dynamic truncation.
- A numeric output.

The implementations use a 30-second interval and six-digit codes.

The calculation is conceptually:

`TOTP = HOTP(Secret, floor(CurrentTime / TimeStep))`

HOTP is the HMAC-based One-Time Password algorithm.

The verification process permits a limited clock-drift window. The demonstrated window includes the previous, current, and next time intervals.

### MFA enrollment workflow

The logical enrollment process is:

`Generate Secret`
       |
`Display Enrollment Information`
       |
`Authenticator Generates Code`
       |
`Verify Initial Code`
       |
`Activate MFA`
       |
`Require MFA During Authentication`

An MFA secret must be protected because anyone who obtains it may be able to generate valid codes.

The PostgreSQL implementation stores encrypted MFA secret material rather than plaintext secrets. Encryption and decryption must be performed through an appropriately controlled application service.

### Other MFA methods

WebAuthn and hardware security keys provide phishing-resistant authentication when correctly implemented.

The SQL model accommodates WebAuthn enrollment as a distinct MFA method.

TOTP is useful for demonstrating MFA mechanics, but it does not provide the same phishing resistance as properly implemented passkeys or security keys.

## 5. Tokens and Sessions

Tokens and sessions represent different approaches to maintaining authenticated state.

### Access tokens

An access token is a credential presented to a resource server to demonstrate authorization granted by an issuer.

The implementations demonstrate signed token structures with:

| Claim | Purpose |
|---|---|
| `sub` | Identifies the subject |
| `iss` | Identifies the issuer |
| `aud` | Identifies the intended audience |
| `iat` | Identifies the issuance time |
| `exp` | Identifies the expiration time |
| `jti` | Identifies a particular token |
| `roles` | Represents role information |

The Python and JavaScript examples implement compact HMAC-signed token models. Java implements an educational signed-token structure with HMAC-SHA-256.

These implementations illustrate signing, signature verification, claim validation, and expiration handling. They are not complete interoperable JWT implementations and should not replace established JWT/OIDC libraries in production.

A valid signature establishes that the signed content has not been modified by an unauthorized party possessing neither the signing key nor another valid signing mechanism.

It does not establish that the token is still authorized. Account disablement, session revocation, permission changes, and token revocation must also be considered.

### Session management

A session maintains server-side authentication state.

The implementations model these states:

| State | Meaning |
|---|---|
| Active | Session can be validated |
| Expired | Session lifetime has ended |
| Revoked | Session has been explicitly invalidated |

The session lifecycle is:

`Authentication -> Session Creation -> Validation -> Expiration or Revocation`

The JavaScript implementation uses `EventEmitter` to communicate session creation and revocation events.

The C++ implementation uses explicit session state and an indexed container.

The Java implementation uses concurrent collections to support concurrent session access.

The PostgreSQL implementation stores hashed session tokens and session metadata.

### Session security

Production session systems should enforce:

- Secure random session identifiers.
- Server-side expiration.
- Session rotation after authentication and privilege changes.
- Explicit logout and revocation.
- Secure, HttpOnly cookies.
- Appropriate SameSite cookie settings.
- TLS for all authentication traffic.
- Session invalidation following account compromise.

A browser cookie should not expose a raw session credential to client-side JavaScript.

### Access tokens versus sessions

| Property | Access token | Server-side session |
|---|---|---|
| Representation | Signed or opaque token | Session identifier |
| State | Often self-contained | Stored on server |
| Validation | Signature or lookup | Server-side lookup |
| Revocation | May require denylist or short lifetime | Server-side invalidation |
| Typical use | API authorization | Web application authentication |

An opaque access token can also use server-side lookup. The distinction is architectural rather than an absolute requirement.

## 6. OAuth 2.0 Concepts

OAuth 2.0 is an authorization framework that allows a client application to obtain limited access to protected resources.

It is not, by itself, an authentication protocol.

OpenID Connect adds an identity layer to OAuth 2.0 and provides standardized mechanisms for authenticating end users.

### Authorization Code Flow

The authorization-code flow involves several participants:

- Resource owner: the user.
- Client: the application requesting access.
- Authorization server: the system issuing authorization grants.
- Resource server: the API protecting resources.

The workflow is:

`User`
  |
`Client Application`
  |
`Authorization Server`
  |
`User Authentication and Consent`
  |
`Authorization Code`
  |
`Client Token Exchange`
  |
`Access Token`
  |
`Resource Server`

The authorization code is an intermediate credential rather than the final API access credential.

### PKCE

Proof Key for Code Exchange protects authorization-code flows against code interception.

PKCE uses two values:

- Code verifier: a high-entropy random value retained by the client.
- Code challenge: a derived value sent during authorization.

The recommended challenge method is `S256`.

The calculation is:

`Code Challenge = BASE64URL(SHA256(Code Verifier))`

During token exchange, the authorization server validates the supplied verifier against the original challenge.

The Python, JavaScript, and Java implementations calculate and validate this relationship.

The PostgreSQL model stores the challenge and a hash of the authorization code. The actual code generation, secure comparison, redirect validation, and token issuance belong to the trusted application layer.

### State parameter

The OAuth `state` parameter helps bind an authorization response to the original authorization request.

It should be unpredictable and validated when the client receives the response.

### Redirect URI validation

Authorization servers must compare redirect URIs against registered client values.

Accepting arbitrary redirect destinations can allow authorization-code leakage and other redirection attacks.

### Authorization-code properties

An authorization code should be:

- Short-lived.
- Bound to a client.
- Bound to a registered redirect URI.
- Bound to the original PKCE challenge.
- Single-use.
- Stored securely.

The implementations demonstrate code expiration and reuse rejection.

## 7. Role-Based Access Control

RBAC assigns permissions to roles and assigns roles to users.

A role represents a defined responsibility or access category.

The fundamental relationship is:

`User -> Role -> Permission`

The implementations define three example roles.

| Role | Profile read | Profile update | Reports read | Manage users | Manage security |
|---|---|---|---|---|---|
| Employee | Yes | Yes | No | No | No |
| Analyst | Yes | No | Yes | No | No |
| Administrator | Yes | Yes | Yes | Yes | Yes |

The RBAC policy engines evaluate effective permissions through assigned roles.

A user with multiple roles receives the permissions granted by those roles, subject to any additional restrictions imposed by the application.

### RBAC implementation decisions

Python uses dictionaries and sets to represent role-permission mappings.

JavaScript uses `Map` and `Set` collections.

C++ uses ordered maps and sets.

Java uses immutable permission sets and an explicit policy object.

PostgreSQL uses four relational structures:

- `users`
- `roles`
- `permissions`
- `user_roles` and `role_permissions`

The database model supports many-to-many relationships between users, roles, and permissions.

### Least privilege

Least privilege means granting only the permissions needed to perform an assigned responsibility.

For example, an analyst may need access to reporting data but should not automatically receive administrative user-management permissions.

Administrative privileges should be limited, monitored, and separated from ordinary user activity.

## 8. Attribute-Based Access Control

ABAC evaluates attributes of the subject, resource, action, and environment.

Unlike RBAC, ABAC does not depend exclusively on role membership.

The general relationship is:

`Subject Attributes + Resource Attributes + Action + Environment -> Policy`

### Subject attributes

Examples:

- User identifier.
- Department.
- Employment status.
- Security clearance.
- Assigned roles.

### Resource attributes

Examples:

- Resource identifier.
- Department ownership.
- Classification level.
- Resource owner.
- Confidentiality classification.

### Environmental attributes

Examples:

- Authentication assurance.
- MFA verification.
- Risk score.
- Network zone.
- Request time.

### Implemented ABAC policies

The implementations demonstrate two authorization scenarios.

**Department-based read access**

A user may read a resource when:

- The account is active.
- The user has completed MFA.
- The risk score does not exceed the configured limit.
- The resource belongs to the user's department, or the user has an administrator role.

**Restricted approval**

A user may approve a resource when:

- The account is active.
- MFA is verified.
- The risk score satisfies the policy.
- The user belongs to the resource department.
- The user's clearance meets the resource classification.
- The user is not the resource owner.

The last condition introduces separation of duties.

### RBAC and ABAC together

RBAC and ABAC solve related but distinct access-control problems.

RBAC answers:

*Does the user's role grant the required permission?*

ABAC answers:

*Do the subject, resource, action, and environmental attributes satisfy the applicable policy?*

The Python, JavaScript, C++, and Java implementations provide independent policy engines.

The SQL implementation evaluates both mechanisms and records their individual results in an authorization audit.

The combined policy follows a restrictive decision model: both checks must allow the requested operation.

## 9. Implementation Architecture

### Python

The Python script provides a self-contained identity service.

Important components:

| Component | Responsibility |
|---|---|
| `PasswordManager` | Password validation, PBKDF2 hashing and verification |
| `TOTP` | MFA code generation and verification |
| `TokenManager` | HMAC token signing and verification |
| `RBAC` | Role-permission evaluation |
| `ABAC` | Attribute-based policy evaluation |
| `OAuthService` | Authorization-code and PKCE workflow |
| `IdentityService` | Registration, authentication and session management |

Python dictionaries provide indexed identity and session lookup.

Sets provide efficient role and permission membership checks.

Dataclasses define user, session, and authorization-code state.

Exceptions distinguish authentication failures from authorization and validation failures.

### JavaScript

The JavaScript implementation uses Node.js standard-library capabilities.

Its main engineering decisions include:

- Asynchronous password hashing with `crypto.pbkdf2`.
- `Map` for client, user, and session indexes.
- `Set` for role and permission membership.
- `EventEmitter` for session lifecycle events.
- Promises for asynchronous credential operations.
- Explicit validation of token claims and OAuth parameters.

The event-driven session service separates session state transitions from the components that consume session events.

The demonstration uses assertions to test incorrect passwords, unauthorized operations, invalid signatures, and reused authorization codes.

### C++17

The C++ implementation emphasizes domain modeling and service separation.

Its components include:

- `IdentityRepository`
- `AuthenticationService`
- `SessionService`
- `RBACPolicy`
- `ABACPolicy`
- `AuthorizationService`
- `TokenValidationService`
- `OAuthClient`

The implementation uses:

- Enumerations for explicit states.
- Structures for domain records.
- Unordered maps for indexed lookups.
- Sets for roles.
- Exceptions for invalid operations.
- Interfaces for cryptographic verification.

The credential-verifier and token-signature-verifier interfaces establish boundaries between access-control logic and cryptographic implementations.

The demonstration verifier is intentionally not a password-hashing mechanism. It must not be used to protect real credentials.

The C++ standard library does not provide a complete production password-hashing, TOTP, JWT, or cryptographic random-number framework. A real implementation must connect these interfaces to appropriate security libraries.

### Java 17

The Java implementation models an enterprise identity service using explicit domain types.

Its components include:

- `User`
- `Session`
- `PasswordRecord`
- `TokenClaims`
- `Resource`
- `Environment`
- `IdentityService`
- `PasswordService`
- `TOTPService`
- `TokenService`
- `OAuthService`
- `RBACPolicy`
- `ABACPolicy`

Records represent immutable data.

Enums represent controlled states.

Concurrent maps support indexed access across concurrent operations.

Atomic counters track authentication failures.

Password hashing uses the Java Cryptography Architecture.

The OAuth authorization-code implementation uses conditional replacement to reduce the risk of concurrent code reuse.

The Java token example is an educational signed-token format, not a complete JWT implementation.

### PostgreSQL

The SQL implementation provides the persistent relational model.

The `identity` schema separates security-related tables from unrelated application data.

Its principal relationships are:

`Users`
  |
  +-- User Roles
  |      |
  |      +-- Roles
  |             |
  |             +-- Role Permissions
  |                    |
  |                    +-- Permissions
  |
  +-- MFA Methods
  |
  +-- Authentication Attempts
  |
  +-- Sessions
  |
  +-- Access Tokens
  |
  +-- OAuth Authorization Codes
  |
  +-- Protected Resources
         |
         +-- Authorization Policies
         |
         +-- Authorization Audit

The database includes:

- Primary and foreign keys.
- Unique constraints.
- Check constraints.
- Partial indexes.
- JSONB resource attributes.
- GIN indexing.
- Views.
- Common table expressions.
- Stored functions.
- Triggers.
- Transactions.
- Audit records.

The `authorize_request` function combines RBAC and ABAC evaluations and records the resulting decision.

## 10. Database Integrity and Workflow Processing

### Account integrity

The `users` table prevents duplicate usernames and email addresses.

It also validates username format, clearance ranges, password algorithm identifiers, and failed-attempt counters.

### Session integrity

The session table records:

- User association.
- Hashed session token.
- Session status.
- Creation time.
- Expiration time.
- Last activity.
- Revocation timestamp.

The session trigger prevents an expired or revoked session from returning to the active state.

### OAuth integrity

The authorization-code table enforces:

- Unique code hashes.
- Registered client association.
- User association.
- Redirect URI.
- PKCE challenge.
- Expiration.
- Grant status.

The trigger prevents a consumed authorization code from returning to the issued state.

A production application must also ensure atomic authorization-code consumption during token exchange.

### Audit records

The authorization audit table records the identity, resource, requested action, decision, reason, and policy context.

Audit information is useful for:

- Security investigations.
- Access reviews.
- Incident analysis.
- Compliance reporting.
- Identification of repeated authorization failures.

Audit tables should have appropriate access restrictions and retention policies.

## 11. Failure Handling and Security Boundaries

| Failure condition | Expected behavior |
|---|---|
| Incorrect password | Reject authentication |
| Excessive failed attempts | Lock account or apply rate limits |
| Missing MFA | Reject authentication |
| Incorrect TOTP | Reject authentication |
| Expired access token | Reject token |
| Invalid signature | Reject token |
| Invalid token audience | Reject token |
| Expired session | Mark session expired |
| Revoked session | Reject session |
| Unregistered OAuth redirect | Reject authorization |
| Invalid PKCE verifier | Reject token exchange |
| Reused authorization code | Reject token exchange |
| Missing RBAC permission | Deny operation |
| ABAC policy failure | Deny operation |
| High-risk request | Deny according to policy |

### Important production limitations

The examples are educational implementations rather than complete identity-provider deployments.

Several security mechanisms require additional production controls:

- Password hashing should use an appropriately configured Argon2id or PBKDF2 implementation.
- Passwords must never be stored in plaintext.
- TOTP secrets should be encrypted at rest.
- MFA enrollment and recovery require secure verification procedures.
- Access-token signing keys must be protected and rotated.
- Token verification must validate algorithm, issuer, audience, expiration, and other required claims.
- Token revocation requires a defined server-side strategy.
- OAuth deployments should follow the applicable security best practices for authorization-code flows, PKCE, redirect validation, and client authentication.
- Session cookies must use appropriate browser security attributes.
- Rate limiting should operate across application instances.
- Account lockout must not provide an easy denial-of-service mechanism.
- Authorization policies should be centrally managed and versioned.
- Audit records must not contain passwords, raw session credentials, authorization codes, or access tokens.
- Administrative actions should be subject to additional monitoring and appropriate privilege separation.

The C++ credential verifier is explicitly a test-only implementation. The Java and Python token structures are educational examples rather than complete standards-compliant token frameworks.

The PostgreSQL functions demonstrate relational policy evaluation, not a replacement for a complete application security boundary. Database privileges must prevent unauthorized direct modifications to security-sensitive tables.

## 12. Performance Considerations

Authentication and authorization involve different computational costs.

| Operation | Typical computational consideration |
|---|---|
| Username lookup | Indexed lookup |
| Password verification | Intentionally expensive key derivation |
| TOTP verification | Small fixed number of HMAC operations |
| Token signature verification | HMAC and claim validation |
| Session lookup | Indexed identifier lookup |
| RBAC evaluation | Role and permission membership checks |
| ABAC evaluation | Attribute retrieval and policy evaluation |
| OAuth code lookup | Indexed lookup and atomic state transition |
| Audit insertion | Database write and index maintenance |

Password hashing should be deliberately expensive enough to resist guessing while remaining operationally manageable.

User, session, token, and authorization-code lookups should use suitable indexes.

For large identity systems, authorization decisions may benefit from caching, but cached permissions must be invalidated when account status, role assignments, or policies change.

## 13. Testing and Validation

The demonstrations include positive and negative security cases.

| Test | Expected result |
|---|---|
| Correct password | Authentication succeeds |
| Incorrect password | Authentication fails |
| Correct TOTP | MFA verification succeeds |
| Incorrect TOTP | MFA verification fails |
| Valid signed token | Token verification succeeds |
| Modified signed token | Verification fails |
| Employee profile permission | Allowed |
| Employee user-management permission | Denied |
| Same-department resource read | Allowed when other ABAC conditions pass |
| High-risk resource access | Denied |
| Registered OAuth redirect | Accepted |
| Incorrect PKCE verifier | Rejected |
| Reused authorization code | Rejected |
| Revoked session | Rejected |

The SQL script also includes retrieval, aggregation, authorization evaluation, reporting, expiration processing, account-lockout handling, and audit queries.

For production testing, concurrent login attempts, token rotation, clock drift, session fixation, authorization bypass, privilege escalation, and distributed rate-limiting behavior should receive dedicated tests.

## 14. Running the Implementations

| File | Execution |
|---|---|
| Python | `python authentication_authorization.py` |
| JavaScript | `node authentication_authorization.js` |
| C++17 | `g++ -std=c++17 -O2 -Wall -Wextra authentication_authorization.cpp -o authentication_authorization` followed by `./authentication_authorization` |
| Java 17 | `javac AuthenticationAuthorization.java` followed by `java AuthenticationAuthorization` |
| PostgreSQL | Execute the SQL script using `psql` against a PostgreSQL database |

The SQL script uses PostgreSQL's `gen_random_uuid()` function and requires a PostgreSQL version supporting that function.

The examples use independent in-memory identity stores except for the PostgreSQL implementation. They do not share credentials, signing keys, or session state.

## 15. Key Technical Distinctions

| Concept | Primary responsibility |
|---|---|
| Authentication | Establish user identity |
| MFA | Strengthen identity verification |
| Password hashing | Protect stored password credentials |
| Access token | Represent an issued access credential |
| Session | Maintain server-side authenticated state |
| OAuth 2.0 | Delegate limited authorization |
| OpenID Connect | Add identity authentication to OAuth 2.0 |
| PKCE | Protect authorization-code exchanges |
| RBAC | Grant permissions through roles |
| ABAC | Evaluate contextual attributes |
| Authorization audit | Record access decisions |

These mechanisms operate together but are not interchangeable.

A valid password does not automatically authorize an operation. An active session does not guarantee that every resource is accessible. A valid token does not eliminate the need to evaluate current authorization policies.

The complete access-control process is:

`Identity Verification`
        |
`MFA Verification`
        |
`Session or Token Establishment`
        |
`Credential Validation`
        |
`RBAC Evaluation`
        |
`ABAC Evaluation`
        |
`Allow or Deny`
        |
`Security Audit`
