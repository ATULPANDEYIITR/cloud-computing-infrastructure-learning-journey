# Key and Secrets Management

## 1. Domain Overview

Key and Secrets Management is the controlled administration of cryptographic keys, application credentials, and digital certificates throughout their operational lifecycles.

These resources protect data confidentiality, integrity, authentication, and secure communication.

The implementations cover four related but distinct areas:

| Area | Primary responsibility | Main security objective |
|---|---|---|
| Encryption key management | Generate, version, rotate, revoke, and retire cryptographic keys | Confidentiality and cryptographic integrity |
| Secrets management | Store and control passwords, tokens, API credentials, and configuration secrets | Prevent unauthorized credential disclosure |
| Certificate management | Maintain certificate identity, validity, expiry, and revocation records | Authentication and trusted communication |
| Security governance | Control permissions, audit operations, and evaluate lifecycle policies | Accountability and controlled access |

A key, a secret, and a certificate are not interchangeable.

- A cryptographic key is mathematical material used by a cryptographic algorithm.
- A secret is sensitive application information, such as a database password or API token.
- A certificate is a digitally signed document binding an identity to a public key and associated attributes.

A certificate does not contain the corresponding private key.

## 2. Cryptographic Key Fundamentals

### 2.1 Symmetric encryption

Symmetric encryption uses the same secret key for encryption and decryption.

AES-256-GCM is used in the JavaScript and Java implementations.

Its principal characteristics are:

- AES uses a 256-bit encryption key.
- GCM provides authenticated encryption.
- The initialization vector (IV) must be unique for each encryption under the same key.
- The authentication tag detects unauthorized ciphertext modification.
- Additional Authenticated Data (AAD) authenticates associated metadata without encrypting it.

For example, a payment record may use its transaction identifier as AAD. This binds the ciphertext to its intended context.

The encryption operation can be represented as:

`Ciphertext, Authentication Tag = AES-GCM(Key, IV, Plaintext, AAD)`

Decryption succeeds only when the authentication tag is valid and the associated data matches.

An application must never accept unauthenticated plaintext after an authentication failure.

### 2.2 Asymmetric cryptography

Asymmetric cryptography uses a public and private key pair.

| Component | Responsibility |
|---|---|
| Public key | Verification or encryption, depending on the algorithm |
| Private key | Signing or decryption, depending on the algorithm |

Ed25519 is a digital-signature algorithm.

Its private key must remain confidential. Its public key can be distributed to parties that need to verify signatures.

The Python and C++ implementations model signing-key metadata and lifecycle policies. The JavaScript and Java implementations concentrate on symmetric authenticated encryption and HMAC operations.

### 2.3 Message authentication

HMAC-SHA256 provides message authentication using a shared secret key.

It can detect unauthorized message modification and verify that a message was produced by a party possessing the shared key.

It does not encrypt the message.

The Python implementation demonstrates:

- HMAC generation.
- HMAC verification.
- Tampered-message rejection.
- Historical verification using a retired key.

The Java implementation provides HMAC functionality through its cryptographic provider.

A MAC must not be treated as a digital signature because both parties possessing the shared secret can generate valid MACs.

## 3. Key Lifecycle Management

Cryptographic keys require controlled lifecycle transitions.

A key should not remain active indefinitely. Its lifecycle must account for algorithm suitability, exposure risk, operational requirements, cryptoperiod, and applicable security policy.

### 3.1 Lifecycle states

| State | Meaning | New encryption | Historical decryption |
|---|---|---|---|
| ACTIVE | Approved for current operations | Allowed | Allowed |
| DECRYPT_ONLY | Retired from new encryption | Denied | Allowed during retention |
| REVOKED | Invalidated because of compromise or policy | Denied | Denied |
| DESTROYED | Material has been removed from the managed provider | Denied | Denied |

The distinction between retirement and revocation is important.

Retirement is a planned lifecycle operation. It permits controlled historical access where policy allows.

Revocation is a security response that invalidates a key because continued use is unacceptable.

Destruction is a separate operation. Removing a reference from an application does not necessarily prove that all physical copies have been securely erased.

### 3.2 Key generation

Key generation must use a cryptographically secure random number generator or an approved cryptographic provider.

The JavaScript implementation uses Node.js `crypto.randomBytes()`.

The Java implementation uses `SecureRandom` through the Java Cryptography Architecture.

The Python implementation uses `secrets.token_bytes()`.

The C++ implementation deliberately delegates material generation to an external cryptographic provider rather than implementing a random-number generator or cryptographic primitive.

The database stores provider references and fingerprints rather than plaintext key material.

### 3.3 Key versioning

Versioning allows a key alias to remain stable while its underlying cryptographic material changes.

Example:

| Alias | Version | State |
|---|---:|---|
| payments/master-key | 1 | DECRYPT_ONLY |
| payments/master-key | 2 | ACTIVE |
| payments/master-key | 3 | Planned |

Applications should resolve the intended version through an authorized key-management interface.

Ciphertext metadata should retain the key identifier and version required for historical decryption.

A version number alone does not identify key material. The key identifier and version together establish the intended cryptographic resource.

### 3.4 Key rotation

Rotation replaces active key material with a new version.

The normal workflow is:

1. Identify the key requiring rotation.
2. Verify authorization and current lifecycle state.
3. Request new key material from the approved provider.
4. Register the new version.
5. Mark the previous version as decrypt-only.
6. Update applications to use the replacement.
7. Re-encrypt or rewrap historical data where required.
8. Verify the migration.
9. Retire or destroy the old material according to retention policy.

Rotation is not equivalent to revocation.

A rotated key may remain necessary for historical decryption. A compromised key may need immediate revocation, with recovery and data migration handled separately.

The Python and JavaScript examples demonstrate key rotation and historical verification or decryption.

The Java implementation uses immutable metadata records to preserve historical state.

The C++ implementation evaluates operation eligibility separately from key lifecycle metadata.

The PostgreSQL procedure performs version transitions within a database transaction.

### 3.5 Rotation failure handling

A production rotation process must account for failures at multiple boundaries:

- The external provider may fail to generate material.
- A new version may be created but not registered.
- The database transaction may fail after the provider operation succeeds.
- Applications may continue using the previous version.
- Historical ciphertext may depend on a version that has been retired prematurely.
- Multiple rotation requests may arrive concurrently.

A database transaction cannot automatically roll back an external KMS operation.

A reliable implementation therefore needs:

- Idempotency keys.
- Durable operation identifiers.
- Rotation status tracking.
- Retry limits.
- Provider reconciliation.
- Controlled activation.
- Recovery procedures.

## 4. Secrets Management

### 4.1 Secret classification

Secrets include:

- Database passwords.
- API access tokens.
- OAuth client secrets.
- Service credentials.
- Private configuration values.
- Application signing credentials.

Secrets must not be placed in source code, public repositories, application logs, or unrestricted configuration files.

The Python implementation models secret creation, reading, versioning, and disabling.

The JavaScript implementation provides an encrypted secret vault backed by AES-256-GCM.

The Java implementation stores secret metadata and demonstrates encrypted storage through the key-management service.

The C++ implementation models secret lifecycle metadata without retaining plaintext credentials.

### 4.2 Secret storage architecture

A production secrets architecture separates secret values from metadata.

The metadata can contain:

- Secret identifier.
- Secret name.
- Version.
- Status.
- Creation time.
- Encryption key identifier.
- Last update time.

The encrypted value should be stored independently from plaintext application access.

A simplified structure is:

    Application
        |
        v
    Authorization Service
        |
        v
    Secrets Manager
        |
        v
    Encrypted Secret Record
        |
        v
    Key Management Service
        |
        v
    External KMS / HSM

The application receives the plaintext only when authorized and when its operation requires it.

Secret retrieval should be minimized and should never return values to unauthorized reporting interfaces.

### 4.3 Secret rotation

Secret rotation changes an application credential without changing the identity of the secret record.

For example:

| Secret | Version | State |
|---|---:|---|
| database/password | 1 | Retired |
| database/password | 2 | Active |

A practical database-password rotation requires coordination between:

- The secrets manager.
- The database authentication system.
- Application connection pools.
- Deployment configuration.
- Credential validation.
- Audit records.

Replacing a stored password without updating the corresponding service credential can cause application outages.

### 4.4 Secret disabling

Disabling a secret prevents ordinary retrieval.

Disabling is not equivalent to revoking the underlying credential at its destination.

For example, disabling an API token in a secrets manager does not automatically invalidate the token at the external API provider.

The destination service must also revoke or invalidate the credential.

## 5. Envelope Encryption

Envelope encryption separates data encryption from master-key management.

It is particularly useful when applications encrypt large amounts of data.

### 5.1 Components

| Component | Purpose |
|---|---|
| Data Encryption Key (DEK) | Encrypts application data |
| Key Encryption Key (KEK) | Protects the DEK |
| Encrypted payload | Authenticated ciphertext |
| Wrapped DEK | Encrypted representation of the data key |
| IV | Unique initialization vector |
| Authentication tag | Verifies ciphertext integrity |
| AAD | Authenticated contextual metadata |

### 5.2 Workflow

    Plaintext
        |
        v
    Generate DEK
        |
        v
    AES-256-GCM Encryption
        |
        +--------------------+
        |                    |
        v                    v
    Ciphertext            DEK
                             |
                             v
                        KEK / KMS
                             |
                             v
                        Wrapped DEK
                             |
                             v
                    Persist both envelopes

Decryption reverses the process:

1. Retrieve the wrapped DEK.
2. Request authorized unwrapping through the KMS.
3. Recover the DEK.
4. Verify the authenticated encryption metadata.
5. Decrypt the application ciphertext.

The JavaScript implementation includes an envelope-encryption service.

The Java implementation demonstrates the generation of a separate data-encryption key and its wrapping through the master-key service.

The PostgreSQL schema includes encrypted payload, IV, authentication tag, wrapped data key, and associated data fields.

### 5.3 Advantages

Envelope encryption reduces the number of operations requiring direct master-key access.

A master key can protect many data-encryption keys.

Master-key rotation can sometimes be performed by rewrapping DEKs rather than decrypting and re-encrypting every application record.

The actual migration strategy depends on the KMS provider and the format of stored ciphertext.

## 6. Access Control and Authorization

Key and secret operations should follow least-privilege access.

The implementations use role-oriented authorization.

| Permission | Capability |
|---|---|
| READ | Read permitted metadata or retrieve authorized secrets |
| WRITE | Create keys and secrets |
| ROTATE | Initiate key rotation |
| REVOKE | Invalidate keys |
| ADMIN | Perform privileged administrative operations |

Example principal assignments:

| Principal | Role | Permissions |
|---|---|---|
| security-admin | SECURITY_ADMIN | All administrative permissions |
| payments-service | APPLICATION | READ, WRITE |
| compliance-auditor | AUDITOR | READ |

A production system should use resource-level authorization.

A principal permitted to access one application's credentials should not automatically receive access to all organizational secrets.

Additional controls include:

- Multifactor authentication for administrators.
- Separation of duties.
- Short-lived access tokens.
- Workload identities.
- Explicit service-to-service authorization.
- Privileged-operation approval.
- Periodic permission reviews.
- Emergency access controls.

The JavaScript and Java implementations separate authorization decisions from key-management operations.

The C++ implementation uses permission sets and explicit policy checks.

The PostgreSQL implementation represents principals, roles, permissions, and assignments relationally.

Database authorization must also be enforced through actual PostgreSQL grants and role restrictions. Application-level permission tables do not independently protect tables from privileged database users.

## 7. Certificate Management

### 7.1 Certificate structure

A digital certificate typically includes:

- Subject identity.
- Issuer identity.
- Serial number.
- Public key.
- Validity period.
- Signature algorithm.
- Certificate extensions.
- Issuer's digital signature.

X.509 certificates are commonly used for TLS authentication and other public-key infrastructure applications.

The implementations maintain certificate inventory metadata. They do not claim to parse, validate, or cryptographically verify complete X.509 certificate chains.

### 7.2 Certificate validity

A certificate must satisfy its validity interval.

    notBefore <= Current Time < notAfter

The certificate inventory uses four principal lifecycle conditions:

| Condition | Meaning |
|---|---|
| VALID | Currently within its validity interval |
| EXPIRING | Approaching its configured renewal threshold |
| EXPIRED | Past its expiration timestamp |
| REVOKED | Explicitly invalidated |

A certificate may also be not yet valid if its `notBefore` time is in the future.

The JavaScript and Java implementations include certificate expiry evaluation.

The C++ implementation rejects certificates that are not yet valid.

The Python implementation maintains certificate fingerprints and expiry metadata.

The PostgreSQL implementation provides both a certificate evaluation function and an inventory view.

### 7.3 Certificate revocation

Certificate revocation is distinct from certificate expiration.

Revocation invalidates a certificate before its natural expiration.

Certificate revocation mechanisms include:

- Certificate Revocation Lists (CRLs).
- Online Certificate Status Protocol (OCSP).

An inventory database records administrative state. It does not automatically provide real-time revocation checking to TLS clients.

Production systems must integrate certificate renewal, trust-chain validation, revocation checking, and service deployment.

### 7.4 Certificate fingerprint

A fingerprint is a digest calculated from certificate data.

The examples use SHA-256 fingerprints for inventory identification.

A fingerprint helps distinguish certificates, but it does not independently prove that a certificate is trusted or that its issuer is legitimate.

Trust validation requires signature verification, chain construction, certificate constraints, validity checks, and appropriate trust anchors.

## 8. Implementation Architecture

### 8.1 Python

The Python implementation uses object-oriented domain modeling and standard-library security facilities.

| Component | Responsibility |
|---|---|
| `EncryptionKey` | Key metadata and lifecycle |
| `KeyManagementService` | Creation, rotation, revocation, HMAC |
| `SecretsManager` | Secret versioning and disabling |
| `CertificateManager` | Certificate inventory and expiry |
| `AccessController` | Permission evaluation |
| `AuditLogger` | Security event collection |
| `evaluate_key_policy()` | Lifecycle compliance |
| `verify_inventory_fingerprints()` | Key-material fingerprint verification |

Python's `secrets` module provides cryptographically strong random bytes.

The implementation uses HMAC-SHA256 for message authentication.

It does not implement AES encryption because the Python standard library does not provide a native authenticated AES-GCM implementation.

The AES-256-GCM algorithm is represented as a supported key type for provider integration, not as an implemented Python encryption operation.

The audit export writes event metadata to a JSON file.

It does not include secret values or raw key material.

### 8.2 JavaScript

The JavaScript implementation uses Node.js built-in cryptographic and event-driven capabilities.

| Component | Responsibility |
|---|---|
| `AuditBus` | Event-driven audit collection |
| `AuthorizationService` | Principal and role checks |
| `LocalKeyProvider` | AES-GCM, HMAC, and key generation |
| `KeyManagementService` | Key lifecycle and encryption |
| `EnvelopeEncryptionService` | DEK generation and wrapping |
| `SecretVault` | Encrypted secret storage |
| `CertificateRegistry` | Certificate metadata and expiry |

The Node.js `crypto` module supplies authenticated encryption.

The implementation uses:

- `createCipheriv()`
- `createDecipheriv()`
- `createHmac()`
- `timingSafeEqual()`
- `randomBytes()`

AES-GCM uses a 12-byte IV and a 16-byte authentication tag.

The audit bus uses `EventEmitter` to publish security events.

The JSON audit export uses restrictive file permissions where supported by the operating system.

The demonstration keeps key material in process memory. A production deployment must replace this local provider with an appropriately protected KMS or HSM.

### 8.3 C++17

The C++ implementation concentrates on domain modeling and governance decisions.

| Component | Responsibility |
|---|---|
| `EncryptionKey` | Typed key metadata |
| `AuthorizationService` | Permission sets |
| `AuditService` | Security event records |
| `KeyManagementEngine` | Lifecycle transitions |
| `SecretsService` | Secret metadata and versions |
| `CertificateService` | Certificate validity |
| `GovernanceReport` | Security inventory |

The implementation uses:

- Enumerations for lifecycle states.
- Structures for domain records.
- `unordered_map` for identifier-based lookup.
- `set` for permission collections.
- `optional` for previous-version relationships.
- STL algorithms for reporting and sorting.
- Exceptions for invalid transitions.

The implementation intentionally does not create its own cryptographic algorithms.

The fingerprint and provider references are illustrative metadata. Actual key material generation, encryption, hashing, and secure destruction require an external cryptographic implementation.

This separation avoids treating an ordinary C++ data structure as a secure key vault.

### 8.4 Java 17

The Java implementation uses an enterprise-oriented service architecture.

| Component | Responsibility |
|---|---|
| `KeyMetadata` | Immutable key metadata |
| `AuthorizationService` | Permission enforcement |
| `AuditService` | Audit event storage |
| `CryptoProvider` | JCA encryption and authentication |
| `KeyManagementService` | Key lifecycle and encrypted operations |
| `EnvelopeEncryptionService` | Data-key protection |
| `SecretVault` | Secret metadata |
| `CertificateService` | Certificate inventory |
| `KeyPolicy` | Lifecycle compliance |

Java records represent immutable metadata.

The Java Cryptography Architecture provides AES-GCM and HMAC operations.

`ReentrantReadWriteLock` separates concurrent metadata reads from lifecycle modifications.

The implementation uses `MessageDigest.isEqual()` for HMAC verification.

The in-memory key repository is a demonstration architecture rather than a durable enterprise KMS.

A production implementation should integrate provider-backed key storage and carefully defined authorization boundaries.

### 8.5 PostgreSQL

The PostgreSQL implementation models a relational key-management workflow.

| Table | Responsibility |
|---|---|
| `organizations` | Organizational ownership |
| `principals` | Users and service identities |
| `roles` | Security roles |
| `permissions` | Available operations |
| `role_permissions` | Role authorization |
| `principal_roles` | Principal assignments |
| `encryption_keys` | Logical key records |
| `key_versions` | Version-specific metadata |
| `key_rotations` | Rotation history |
| `secrets` | Secret identity and lifecycle |
| `secret_versions` | Encrypted secret envelopes |
| `certificates` | Certificate inventory |
| `key_usage` | Cryptographic operation records |
| `audit_events` | Administrative event history |

The design separates logical keys from individual key versions.

This allows a stable key alias to reference multiple versions throughout its lifecycle.

Foreign keys enforce relationships between organizations, principals, keys, versions, and secrets.

Check constraints enforce validity intervals and data-format requirements.

Triggers enforce key-version and secret-key consistency.

Stored procedures implement key and secret rotation workflows.

Views simplify key, secret, and certificate reporting.

CTEs aggregate security posture across organizations.

Partial indexes support queries involving active keys, unrevoked certificates, and unsuccessful security operations.

## 9. Database Relationships

The relational model can be represented as:

    ORGANIZATION
        |
        +---- PRINCIPALS
        |        |
        |        +---- PRINCIPAL_ROLES
        |        |         |
        |        |         +---- ROLES
        |        |                   |
        |        |                   +---- ROLE_PERMISSIONS
        |        |                               |
        |        |                               +---- PERMISSIONS
        |        |
        |        +---- KEY_USAGE
        |
        +---- ENCRYPTION_KEYS
        |        |
        |        +---- KEY_VERSIONS
        |        |        |
        |        |        +---- KEY_ROTATIONS
        |        |
        |        +---- SECRET_VERSIONS
        |
        +---- SECRETS
        |        |
        |        +---- SECRET_VERSIONS
        |
        +---- CERTIFICATES
        |
        +---- AUDIT_EVENTS

`encryption_keys` represents logical cryptographic resources.

`key_versions` represents individual generations of cryptographic material.

`key_rotations` records administrative transitions.

`secret_versions` links encrypted secret records to the key version protecting them.

The encrypted payload and wrapped data key remain separate from key metadata.

## 10. Security Policy Evaluation

Key lifecycle policy should evaluate multiple conditions rather than checking only whether a key exists.

Typical policy conditions include:

| Policy | Evaluation |
|---|---|
| Algorithm approval | Is the algorithm approved for the intended operation? |
| Key age | Does the key exceed its maximum cryptoperiod? |
| Expiration | Is the key still within its validity period? |
| Lifecycle state | Is the key active or retired? |
| Access authorization | Does the principal have the required permission? |
| Version integrity | Does the requested version belong to the intended key? |
| Fingerprint integrity | Does the recorded fingerprint match provider metadata? |
| Revocation | Has the key or certificate been invalidated? |

The Python `evaluate_key_policy()` function evaluates lifecycle compliance.

The Java `KeyPolicy` class returns a list of policy violations.

The C++ implementation evaluates whether a key can perform an operation.

The PostgreSQL `key_is_eligible()` function provides database-level operation eligibility.

Eligibility is not the same as authorization.

A key may be technically eligible for encryption while a particular application principal remains unauthorized to use it.

Likewise, an authorized principal cannot use a revoked key.

## 11. Failure Scenarios and Controls

| Failure scenario | Risk | Appropriate control |
|---|---|---|
| Key compromise | Unauthorized decryption or signing | Revoke and replace the compromised key |
| Expired key | Unavailable cryptographic operations | Automated expiry monitoring |
| Reused GCM IV | Loss of cryptographic security | Unique IV generation |
| Modified ciphertext | Unauthorized data alteration | Authenticated decryption |
| Unauthorized secret access | Credential disclosure | Least-privilege authorization |
| Stale application credential | Service authentication failure | Coordinated secret rotation |
| Incorrect key version | Historical data unavailable | Persist key identifier and version |
| Failed rotation | Inconsistent provider and database state | Durable rotation workflow and reconciliation |
| Expired certificate | TLS connection failure | Renewal monitoring |
| Revoked certificate | Trust failure | Revocation checking |
| Missing audit record | Reduced accountability | Centralized durable audit collection |
| Duplicate certificate | Incorrect inventory association | Fingerprint uniqueness |
| Concurrent rotation | Conflicting active versions | Transactional locking and idempotency |

### 11.1 Authentication failures

Authenticated encryption must fail closed.

A decryption operation must not return plaintext when its authentication tag is invalid.

The JavaScript implementation tests ciphertext tampering.

The Java implementation tests altered ciphertext and expects authenticated decryption to reject it.

### 11.2 Authorization failures

The application principal cannot perform administrative key rotation.

The demonstrations intentionally test unauthorized rotation.

A denial should be recorded without disclosing sensitive key material or secret values.

### 11.3 Key destruction

Key destruction must consider:

- Existing ciphertext dependencies.
- Backup retention.
- Wrapped data keys.
- Replicated key material.
- Provider retention policies.
- Legal retention requirements.
- Recovery requirements.

Destroying an encryption key before migrating dependent data may permanently prevent recovery.

## 12. Performance and Scalability

Key management has different performance characteristics from bulk data encryption.

### 12.1 Cryptographic operation performance

Bulk data encryption should normally occur through a data-encryption key rather than repeatedly using a remote master key.

Envelope encryption limits the frequency of master-key operations.

### 12.2 Metadata lookup

The C++ and Java implementations use hash-based structures for identifier lookups.

The Python implementation uses dictionaries.

The JavaScript implementation uses `Map`.

Expected lookup complexity is approximately O(1) for ordinary hash-table operations.

The PostgreSQL implementation uses primary keys and supporting indexes to accelerate resource lookup.

### 12.3 Concurrency

Concurrent key rotation must be controlled.

Two rotation requests must not independently activate competing versions.

The Java implementation uses read/write locks.

The PostgreSQL procedure locks the parent key and its active version.

A distributed KMS integration also needs idempotent provider requests and durable workflow state.

### 12.4 Audit volume

Key operations can produce substantial audit traffic.

Production systems should consider:

- Time-based partitioning.
- Indexed retrieval.
- Retention periods.
- Centralized logging.
- Restricted audit modification.
- Archival policies.
- Security monitoring.

Audit records should not contain passwords, plaintext keys, authentication tokens, or decrypted secret values.

## 13. Production Security Considerations

The source files demonstrate security-oriented workflows, but an in-memory example is not equivalent to a production key-management platform.

Production deployment requires the following controls.

### Cryptographic provider

- Use an approved KMS or HSM.
- Restrict access to raw private and symmetric key material.
- Use approved cryptographic algorithms.
- Validate key sizes and provider configuration.
- Define cryptoperiods.
- Separate development, staging, and production keys.

### Application security

- Use TLS for service communication.
- Authenticate workload identities.
- Apply resource-level authorization.
- Avoid logging secret values.
- Minimize plaintext memory exposure.
- Use short-lived credentials.
- Protect application configuration.
- Implement rate limiting and monitoring.

### Database security

- Restrict database ownership.
- Apply explicit `GRANT` and `REVOKE` statements.
- Prevent unrestricted direct modification of key metadata.
- Encrypt database backups.
- Restrict access to encrypted secret payloads.
- Separate application and administrative database roles.
- Protect audit data from unauthorized modification.

### Operational security

- Monitor expiring keys and certificates.
- Maintain documented emergency revocation procedures.
- Test recovery from provider failures.
- Verify historical decryption before key retirement.
- Reconcile external KMS state with database records.
- Review privileged operations.
- Establish retention and destruction policies.

### Compliance

Key-management controls may support organizational security requirements, including cryptographic governance, access accountability, and controlled credential handling.

Actual compliance depends on the implemented environment, operational evidence, applicable regulations, and independent assessment.

## 14. Execution

### Python

Requirements:

- Python 3.10 or later.
- Standard library only.

Run:

`python key_management.py`

The program generates an HMAC key, verifies messages, rotates the key, manages a secret, registers a certificate, evaluates policy, and exports `security_audit.json`.

The file contains audit metadata rather than plaintext secret values.

### JavaScript

Requirements:

- Node.js 20 or later.
- No third-party npm dependencies.

Run:

`node key_management.js`

The program demonstrates AES-256-GCM encryption, authenticated decryption, tampering detection, envelope encryption, secret versioning, key rotation, and certificate inventory.

It writes `security_audit.json`.

### C++17

Requirements:

- C++17-compatible compiler.
- No external libraries.

Compile:

`g++ -std=c++17 -O2 -Wall -Wextra -pedantic key_management.cpp -o key_management`

Run:

`./key_management`

On Windows:

`key_management.exe`

The program demonstrates lifecycle transitions, authorization, governance checks, secret metadata, certificate validation, and audit reporting.

It does not perform cryptographic encryption.

### Java 17

Requirements:

- Java 17.
- Standard Java Cryptography Architecture.

Compile:

`javac KeyManagement.java`

Run:

`java KeyManagement`

The program demonstrates AES-256-GCM encryption, authenticated decryption, key rotation, secret metadata, certificate inventory, and policy evaluation.

### PostgreSQL

Requirements:

- PostgreSQL 15 or later.
- Database privileges sufficient to create schemas, tables, functions, procedures, and triggers.

Execute the SQL file against a dedicated development database.

The script:

- Creates the `key_management` schema.
- Defines domain types.
- Creates relational tables and indexes.
- Defines triggers and stored procedures.
- Inserts demonstration records.
- Executes reporting and validation queries.
- Demonstrates transactional key rotation.

The sample IV, authentication tag, encrypted payload, and wrapped data key are illustrative binary values. They are not valid production ciphertext.

## 15. Limitations and Design Boundaries

The implementations deliberately distinguish cryptographic operations from metadata and lifecycle management.

| Implementation | Implemented cryptographic functionality | Important limitation |
|---|---|---|
| Python | Secure random generation, SHA-256 fingerprints, HMAC-SHA256 | No native AES-GCM implementation |
| JavaScript | AES-256-GCM, HMAC-SHA256, secure random generation | In-memory key material is not an HSM |
| C++17 | Governance and operation eligibility | Cryptographic provider is external |
| Java 17 | AES-256-GCM, HMAC-SHA256, secure random generation | Demonstration key repository is in memory |
| PostgreSQL | Metadata, relationships, integrity constraints, workflow procedures | Encryption and KMS operations occur outside the database |

Other limitations include:

- The certificate examples maintain inventory metadata rather than validating complete X.509 trust chains.
- The local key providers do not provide enterprise hardware-backed isolation.
- The demonstration audit records are not independently tamper-proof.
- Application authorization requires corresponding production identity and database controls.
- In-memory repositories do not survive process termination.
- Secure deletion cannot be guaranteed by clearing an ordinary application reference.
- The database cannot provide atomic transactions across an external KMS and PostgreSQL without an additional distributed workflow.

These boundaries are important because key management is a security infrastructure responsibility, not simply a collection of encryption functions.

## 16. Core Technical Distinctions

| Concept | What it controls | What it does not automatically guarantee |
|---|---|---|
| Encryption | Data confidentiality | Authorization |
| Authentication tag | Ciphertext integrity and authenticity under the key | Identity of an individual sender |
| HMAC | Shared-key message authentication | Confidentiality or non-repudiation |
| Key rotation | Replacement of cryptographic material | Revocation of compromised external credentials |
| Key revocation | Invalidates further permitted use | Recovery of already exposed plaintext |
| Secret rotation | Replacement of sensitive credentials | Revocation at the destination service |
| Certificate renewal | Replacement of an expiring certificate | Automatic deployment to every service |
| Certificate revocation | Invalidates certificate trust | Immediate enforcement by every relying party |
| Envelope encryption | Separation of data keys and master keys | Protection from an authorized compromised application |
| Audit logging | Records security events | Prevention of unauthorized operations |

The central architectural principle is to separate cryptographic material, encrypted application data, secret values, certificate identity, authorization decisions, and lifecycle metadata.

Each component has a distinct responsibility and must be governed through explicit security policies.
