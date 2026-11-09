# Encryption Fundamentals

## 1. Introduction

Encryption is a security mechanism that transforms readable information into ciphertext using a cryptographic algorithm and a key. Only an authorized party possessing the appropriate decryption capability can recover the original information.

Encryption protects information against unauthorized disclosure when data is stored, transmitted, or exchanged between systems.

The four principal areas covered in this project are:

1. Encryption at rest.
2. Encryption in transit.
3. Symmetric encryption.
4. Asymmetric encryption.

These areas describe different aspects of information security. Encryption at rest and encryption in transit describe where data is protected. Symmetric and asymmetric encryption describe how cryptographic keys are used.

A system can combine these mechanisms rather than selecting only one.

## 2. Fundamental Terminology

| Term | Meaning |
|---|---|
| Plaintext | Original readable information before encryption. |
| Ciphertext | Encrypted information produced by an encryption algorithm. |
| Encryption | Transformation of plaintext into ciphertext. |
| Decryption | Recovery of plaintext from ciphertext. |
| Cryptographic key | Secret or private information controlling a cryptographic operation. |
| Key pair | Related public and private keys used in asymmetric cryptography. |
| Nonce | Value used once with a particular cryptographic key and algorithm. |
| Initialization vector | Input used by certain encryption modes to initialize encryption operations. |
| Authentication tag | Cryptographic value used to verify ciphertext integrity and authenticity. |
| Associated data | Additional authenticated information that is protected against modification but remains unencrypted. |
| Key rotation | Replacement of an existing cryptographic key with a new key. |
| Key revocation | Invalidating a key so that it cannot be used for authorized cryptographic operations. |
| Digital signature | Cryptographic evidence that a message was signed using a particular private key. |
| Certificate | Signed document binding a public key to an identity or other attributes. |
| TLS | Transport Layer Security, a protocol protecting communication between network endpoints. |
| KMS | Key Management Service responsible for managing cryptographic keys. |
| HSM | Hardware Security Module designed to protect cryptographic operations and key material. |
| Envelope encryption | Encryption of data using a data-encryption key, followed by protection of that key using another cryptographic key. |

## 3. Encryption Architecture

The relationship between the four principal concepts can be represented as follows:

| Perspective | Category | Main concern |
|---|---|---|
| Data location | At rest | Protecting stored information. |
| Data location | In transit | Protecting information during communication. |
| Cryptographic mechanism | Symmetric | Using the same secret key for encryption and decryption. |
| Cryptographic mechanism | Asymmetric | Using mathematically related public and private keys. |

An enterprise application may use all four mechanisms:

- AES-256-GCM encrypts confidential database records.
- TLS protects communication between the application and database.
- RSA-OAEP protects an AES data-encryption key.
- A digital signature verifies the origin and integrity of a signed message.

---

## 4. Symmetric Encryption

### 4.1 Concept

Symmetric encryption uses the same secret key for encryption and decryption.

The sender and recipient must possess the same secret key or have access to a shared key-management system.

The general process is:

Plaintext + Secret Key
        |
        v
   Encryption
        |
        v
     Ciphertext
        |
        v
   Decryption
        |
        v
Plaintext + Same Secret Key

The primary advantage is computational efficiency. Symmetric encryption is suitable for large files, database records, backups, and continuous data streams.

The main challenge is secure key distribution and management.

### 4.2 AES

Advanced Encryption Standard (AES) is a widely deployed symmetric block cipher.

Its standard key sizes are:

| AES variant | Key size | Block size |
|---|---:|---:|
| AES-128 | 128 bits | 128 bits |
| AES-192 | 192 bits | 128 bits |
| AES-256 | 256 bits | 128 bits |

AES-256 uses a 256-bit key and performs 14 encryption rounds.

The implementations use AES-256-GCM.

### 4.3 Galois/Counter Mode

Galois/Counter Mode (GCM) combines encryption with authentication.

It provides:

- Confidentiality.
- Ciphertext integrity.
- Authentication of encrypted content.
- Authentication of associated data.

Unlike encryption modes that provide confidentiality alone, GCM also detects unauthorized modifications.

The encryption result contains:

- Nonce.
- Ciphertext.
- Authentication tag.

The receiver must verify the authentication tag before accepting decrypted information.

If authentication fails, the plaintext must not be treated as valid.

### 4.4 Nonce Management

GCM requires careful nonce management.

The standard nonce length used in these implementations is 96 bits, or 12 bytes.

A nonce must not be reused with the same key.

Nonce reuse can seriously compromise confidentiality and authentication.

The Python, JavaScript, and Java implementations generate nonces using cryptographically secure random-number generators.

A production system must also consider collision probability, key usage limits, and distributed nonce allocation.

### 4.5 Symmetric Encryption Implementation

| File | Implementation |
|---|---|
| Python | `SymmetricEncryption` |
| JavaScript | `AESGCMService` |
| C++17 | Algorithm and authentication policy evaluation |
| Java 17 | `AESGCMService` |
| PostgreSQL | Algorithm catalog and encryption-operation records |

The implementations validate key length, reject invalid parameters, and verify authentication during decryption.

---

## 5. Asymmetric Encryption

### 5.1 Concept

Asymmetric encryption uses two mathematically related keys:

- Public key.
- Private key.

The public key can be distributed to other parties. The private key must remain confidential.

A sender can encrypt information using the recipient's public key. The recipient decrypts it using the corresponding private key.

Encryption workflow:

Sender
  |
  v
Recipient's Public Key
  |
  v
Asymmetric Encryption
  |
  v
Ciphertext
  |
  v
Recipient's Private Key
  |
  v
Decryption
  |
  v
Original Information

This architecture reduces the requirement to distribute a shared encryption secret to every communicating party.

It does not eliminate key management. Public-key authenticity, private-key protection, certificate validation, and revocation remain essential.

### 5.2 RSA

Rivest-Shamir-Adleman (RSA) is an asymmetric cryptographic algorithm based on the mathematical difficulty of factoring large integers.

RSA supports encryption and digital signatures through different cryptographic schemes.

The implementations use:

`RSA-OAEP-SHA256`

OAEP stands for Optimal Asymmetric Encryption Padding.

It provides a randomized padding construction for RSA encryption.

SHA-256 is used as the OAEP hash function.

The examples use 3072-bit RSA keys.

### 5.3 RSA Limitations

RSA is computationally more expensive than symmetric encryption.

It also has a strict plaintext size limit determined by the modulus size, padding scheme, and hash length.

Consequently, RSA is not appropriate for directly encrypting large files or database records.

A practical design uses RSA to protect a randomly generated symmetric key.

### 5.4 Digital Signatures

Digital signatures provide a mechanism for verifying message authenticity and integrity.

A sender signs a message using a private signing key.

A recipient verifies the signature using the corresponding public key.

The examples use RSA-PSS with SHA-256.

| Property | Encryption | Digital signature |
|---|---|---|
| Primary objective | Confidentiality | Authenticity and integrity |
| Operation | Encrypt | Sign |
| Key generally used | Recipient public key | Sender private key |
| Verification or recovery | Recipient private key | Sender public key |
| Typical application | Confidential communication | Signed transactions and software artifacts |

Encryption and digital signatures are separate security mechanisms.

Encryption does not automatically prove who created a message.

A digital signature does not automatically make a message confidential.

---

## 6. Encryption at Rest

### 6.1 Concept

Encryption at rest protects information stored on persistent storage systems.

Examples include:

- Database records.
- Database backups.
- File systems.
- Cloud object storage.
- Application documents.
- Archived transaction records.
- Configuration backups.

The primary objective is to prevent unauthorized access to stored information.

### 6.2 Encryption Workflow

Original File
    |
    v
Read Plaintext
    |
    v
Retrieve Active Encryption Key
    |
    v
Generate Unique Nonce
    |
    v
AES-256-GCM Encryption
    |
    v
Store Ciphertext and Authentication Tag
    |
    v
Persist Encrypted File

Decryption requires the correct key and successful authentication.

### 6.3 File Format

The Python and JavaScript implementations use a structured encrypted-file format.

| Component | Purpose |
|---|---|
| Magic identifier | Identifies the encrypted-file format. |
| Metadata length | Defines the size of the metadata section. |
| Metadata | Stores the algorithm and key identifier. |
| Nonce | Provides the GCM initialization value. |
| Authentication tag | Verifies integrity and authenticity. |
| Ciphertext | Contains the encrypted file content. |

The key itself is not included in the encrypted file.

The key identifier allows the application to retrieve the appropriate key from the key-management subsystem.

### 6.4 Encryption at Rest Versus Storage Permissions

Encryption and access permissions solve different problems.

| Control | Protection |
|---|---|
| File permissions | Restrict access through operating-system identities. |
| Database permissions | Restrict access through database authorization. |
| Disk encryption | Protect storage media and offline data access. |
| Application-level encryption | Protect selected records before storage. |
| Backup encryption | Protect copied and archived information. |

Storage encryption does not automatically protect data after an authorized application decrypts it.

An attacker controlling an authorized application or compromised endpoint may still obtain plaintext.

### 6.5 Practical Considerations

- Store encryption keys separately from encrypted data.
- Use authenticated encryption.
- Apply access restrictions to encrypted files.
- Protect temporary files.
- Avoid exposing plaintext in logs.
- Maintain key recovery procedures.
- Test restoration from encrypted backups.
- Ensure old encryption keys remain available for legitimate decryption during migration.

---

## 7. Encryption in Transit

### 7.1 Concept

Encryption in transit protects information while it travels between two or more systems.

Examples include:

- Browser-to-server communication.
- Application-to-database connections.
- Microservice communication.
- API requests.
- Remote administrative sessions.
- Cloud service communication.

TLS is the primary transport security protocol demonstrated in this project.

### 7.2 TLS Architecture

TLS establishes a protected communication channel between endpoints.

A simplified workflow is:

Client
  |
  v
Connect to Server
  |
  v
TLS Handshake
  |
  v
Certificate Validation
  |
  v
Key Agreement
  |
  v
Session Key Establishment
  |
  v
Authenticated Encrypted Communication

The TLS handshake establishes cryptographic parameters and session secrets.

Modern TLS uses authenticated encryption for application data.

The actual TLS protocol includes additional details such as transcript authentication, key derivation, certificate authentication, and handshake state management.

### 7.3 TLS Certificate Validation

Certificate validation establishes whether the server's presented certificate is trusted for the intended identity.

Important checks include:

- Certificate chain validation.
- Certificate validity period.
- Trusted certificate authority.
- Hostname matching.
- Key usage and extended key usage.
- Revocation policy where supported and required.

A connection that encrypts traffic without validating the intended server's identity may remain vulnerable to an active intermediary.

### 7.4 TLS Versions

| Version | Characteristics |
|---|---|
| TLS 1.2 | Widely supported secure transport protocol with appropriate modern cipher suites and configuration. |
| TLS 1.3 | Simplified handshake and modern cryptographic configuration. |

The Python and JavaScript implementations configure TLS 1.2 as their minimum supported version.

The JavaScript implementation enables certificate verification.

The Python implementation uses the platform trust configuration and hostname verification.

A production deployment should generally prefer TLS 1.3 where compatible.

### 7.5 Encryption in Transit Versus Encryption at Rest

| Characteristic | At rest | In transit |
|---|---|---|
| Protected object | Stored information | Communicated information |
| Typical mechanism | AES-GCM | TLS |
| Key requirement | Storage encryption key | Session secrets and certificate-related keys |
| Main threat | Unauthorized storage access | Interception and modification |
| Common failure | Lost or exposed storage key | Invalid certificate or weak TLS configuration |
| Verification | Authentication tag | TLS authentication and record protection |

Using encryption at rest does not replace TLS.

Using TLS does not guarantee that information remains encrypted after reaching its destination.

---

## 8. Hybrid Encryption

### 8.1 Concept

Hybrid encryption combines symmetric and asymmetric cryptography.

It uses symmetric encryption for the actual data and asymmetric encryption to protect the symmetric data-encryption key.

This approach combines the performance of symmetric cryptography with the key-distribution capabilities of asymmetric cryptography.

### 8.2 Hybrid Encryption Workflow

Original Data
    |
    v
Generate Random AES Data Key
    |
    +---------------------------+
    |                           |
    v                           v
AES-256-GCM Encryption     RSA-OAEP Encryption
    |                           |
    v                           v
Ciphertext                 Wrapped AES Key
    |                           |
    +-------------+-------------+
                  |
                  v
            Hybrid Envelope
                  |
                  v
          Recipient Receives
                  |
                  v
        RSA Private-Key Decryption
                  |
                  v
           Recover AES Key
                  |
                  v
           AES-GCM Decryption
                  |
                  v
             Original Data

### 8.3 Envelope Structure

The Python, JavaScript, and Java implementations use a structured envelope containing:

| Field | Purpose |
|---|---|
| Version | Identifies the envelope format. |
| Algorithm | Defines the cryptographic construction. |
| Wrapped key | AES data key encrypted with the recipient's RSA public key. |
| Nonce | AES-GCM nonce. |
| Ciphertext | Encrypted application data. |
| Authentication tag | Verifies ciphertext integrity. |

The envelope uses associated data to bind the encrypted content to its expected context.

### 8.4 Why Hybrid Encryption Is Preferred

| Requirement | Symmetric encryption | Asymmetric encryption | Hybrid encryption |
|---|---|---|---|
| Large data encryption | Suitable | Inefficient | Suitable |
| Key distribution | Shared secret required | Public key can be distributed | Public-key protection of data key |
| Performance | High | Lower | High for data encryption |
| Confidentiality | Yes | Yes | Yes |
| Authentication | Depends on construction | Depends on construction | Provided by authenticated symmetric encryption |

Hybrid encryption is widely used in secure communication and data exchange architectures.

It is important to distinguish a hybrid encryption envelope from TLS. TLS is a complete transport protocol with authentication, negotiation, key derivation, record protection, and protocol-state requirements. A basic hybrid envelope does not implement TLS.

---

## 9. Key Management

### 9.1 Importance of Key Management

Cryptographic security depends on protecting keys throughout their lifecycle.

A strong encryption algorithm cannot compensate for an exposed private key or poorly managed symmetric key.

The project models the following lifecycle:

Key Creation
    |
    v
Key Activation
    |
    v
Authorized Encryption
    |
    v
Periodic Rotation
    |
    v
Previous Key Retirement
    |
    v
Historical Decryption
    |
    v
Controlled Revocation

### 9.2 Key States

| State | Meaning |
|---|---|
| ACTIVE | Available for authorized cryptographic operations. |
| RETIRED | No longer used for new encryption but may remain available for historical decryption. |
| REVOKED | Invalidated and unavailable for normal cryptographic operations. |

Retirement and revocation have different operational implications.

A retired key may still be needed to decrypt older encrypted records.

Revoking a key may prevent further access to encrypted information unless a valid recovery mechanism exists.

### 9.3 Key Rotation

Key rotation replaces an existing key with a new key.

A complete rotation workflow may involve:

1. Generate a new key.
2. Register the new key in the key-management system.
3. Activate the replacement key.
4. Stop using the previous key for new encryption.
5. Re-encrypt existing data where required.
6. Verify successful migration.
7. Retain the old key for authorized historical decryption.
8. Revoke or destroy the old key according to retention policy.

Creating a replacement key does not automatically re-encrypt existing data.

The Python and JavaScript demonstrations retain retired keys for historical decryption.

The PostgreSQL procedure records a new key version and retires the previous active key. It does not perform data re-encryption.

### 9.4 KMS and HSM

A Key Management Service centralizes key lifecycle operations.

A Hardware Security Module provides hardware-backed protection for sensitive cryptographic operations and key material.

Common responsibilities include:

- Key generation.
- Key storage.
- Access control.
- Rotation.
- Revocation.
- Key usage auditing.
- Backup and recovery.
- Separation of administrative responsibilities.

The Python and JavaScript examples use in-memory key managers for demonstration. They are not persistent production key vaults.

The database stores external key references rather than raw cryptographic key material.

---

## 10. Implementation Architecture

### 10.1 Python

The Python implementation emphasizes modular cryptographic operations and file workflows.

| Component | Responsibility |
|---|---|
| `SymmetricEncryption` | AES-256-GCM encryption and decryption. |
| `AsymmetricEncryption` | RSA-OAEP encryption and RSA-PSS signatures. |
| `HybridEncryption` | AES data encryption and RSA key wrapping. |
| `KeyManager` | Key creation, rotation, retirement, and revocation. |
| `SecureFileStorage` | Authenticated encryption of files at rest. |
| `TransportSecurity` | Secure TLS client configuration. |
| `EncryptionTests` | Automated validation and failure testing. |

The implementation uses the `cryptography` package because Python's standard library does not provide a complete AES-GCM and RSA-OAEP implementation.

### 10.2 JavaScript

The JavaScript implementation uses Node.js built-in cryptographic and filesystem capabilities.

| Component | Responsibility |
|---|---|
| `AESGCMService` | Authenticated symmetric encryption. |
| `RSAService` | Asymmetric encryption and digital signatures. |
| `HybridEncryption` | Hybrid envelope processing. |
| `KeyVault` | In-memory key lifecycle management. |
| `EncryptedFileStore` | Asynchronous encrypted file handling. |
| `TLSConfiguration` | Secure transport configuration. |
| `EncryptionAudit` | SHA-256 fingerprinting and comparison. |

The file-storage workflow uses asynchronous filesystem operations, unique temporary filenames, restricted file permissions, and atomic replacement.

### 10.3 C++17

The C++ implementation focuses on security policy and cryptographic architecture.

The C++17 standard library does not provide AES-GCM, RSA-OAEP, or TLS implementations.

The implementation therefore avoids presenting an invented encryption algorithm as secure cryptography.

| Component | Responsibility |
|---|---|
| `EncryptionPolicy` | Defines encryption requirements. |
| `KeyRegistry` | Tracks key states and key versions. |
| `SecurityPolicyEngine` | Evaluates encryption eligibility. |
| `CryptographicProvider` | Defines the boundary for an external cryptographic implementation. |
| `EnvelopeValidator` | Validates encrypted-envelope metadata. |
| `EvaluationResult` | Reports policy decisions and rejection reasons. |

A production cryptographic provider must implement actual encryption and decryption using an independently validated cryptographic implementation.

The policy engine demonstrates how an enterprise application can separate security decisions from cryptographic execution.

### 10.4 Java 17

The Java implementation uses the Java Cryptography Architecture (JCA) and Java Cryptography Extension (JCE).

| Component | Responsibility |
|---|---|
| `AESGCMService` | AES-GCM encryption and decryption. |
| `RSAService` | RSA-OAEP and RSA-PSS operations. |
| `HybridEncryptionService` | Data-key generation and RSA key wrapping. |
| `KeyVault` | Key lifecycle and metadata management. |
| `PolicyService` | Encryption policy evaluation. |
| `EncryptionPolicy` | Immutable policy definition. |
| `HybridEnvelope` | Structured encrypted-message representation. |

Java records represent immutable domain data, while service classes manage cryptographic operations.

### 10.5 PostgreSQL

The SQL implementation models the relational security-management workflow.

| Database object | Responsibility |
|---|---|
| `security_principals` | Identifies authorized actors and service identities. |
| `applications` | Registers enterprise applications. |
| `algorithms` | Maintains approved cryptographic algorithms. |
| `encryption_keys` | Maintains external key references and lifecycle states. |
| `key_lifecycle_events` | Records key state transitions. |
| `encryption_policies` | Defines encryption requirements. |
| `protected_resources` | Registers protected information assets. |
| `encryption_operations` | Records encryption and decryption activities. |
| `transport_connections` | Records transport security properties. |
| `security_audit_events` | Stores security-related events. |

The schema uses primary keys, foreign keys, unique constraints, check constraints, indexes, views, functions, procedures, triggers, and transactions.

PostgreSQL manages the security metadata. The application or external cryptographic service performs the actual encryption.

---

## 11. Database Workflow

The relational model follows this relationship:

Security Principals
        |
        v
    Applications
        |
        +----------------------+
        |                      |
        v                      v
 Encryption Keys       Protected Resources
        |                      |
        v                      v
 Key Lifecycle         Encryption Policies
        |                      |
        +----------+-----------+
                   |
                   v
          Encryption Operations
                   |
                   v
          Security Audit Events

Transport connections are independently associated with applications because transport protection is evaluated at the communication boundary.

### 11.1 Integrity Controls

The schema includes:

- Primary keys for entity identification.
- Foreign keys for relationship integrity.
- Unique external key references.
- Unique application key versions.
- A partial unique index restricting each application to one active key.
- Check constraints for key states and transport versions.
- Triggers for key lifecycle auditing.
- Triggers for protected-resource state validation.

### 11.2 Policy Evaluation

The `evaluate_encryption_request` function checks:

1. Resource existence.
2. Enabled encryption policy.
3. Approved algorithm.
4. Encryption category.
5. Authentication requirements.
6. Nonce uniqueness requirements.
7. Certificate validation.
8. TLS version.
9. Key availability.
10. Application ownership of the key.
11. Key and algorithm compatibility.

The function returns a decision and a list of rejection reasons.

### 11.3 Transaction Handling

The `rotate_application_key` procedure performs key-version management within the caller's transaction.

The procedure checks the caller's registered role, retires the previous active key, creates the new key reference, and records an audit event.

If any operation fails, the surrounding transaction can be rolled back.

The procedure manages metadata and does not generate or retrieve cryptographic key material.

---

## 12. Security Controls and Failure Handling

| Failure condition | Required response |
|---|---|
| Incorrect AES key length | Reject the encryption operation. |
| Invalid nonce length | Reject the cryptographic input. |
| Reused GCM nonce | Prevent encryption under the affected key and investigate. |
| Modified ciphertext | Reject authentication. |
| Incorrect authentication tag | Do not release plaintext. |
| Invalid RSA ciphertext | Reject decryption. |
| Unknown key identifier | Reject the operation. |
| Revoked key | Deny normal key usage. |
| Expired or invalid certificate | Reject the TLS connection. |
| Hostname mismatch | Reject the TLS connection. |
| Weak TLS version | Deny connections under policy. |
| Unapproved algorithm | Reject policy evaluation. |
| Missing key-management permission | Reject administrative action. |
| Failed file operation | Remove incomplete temporary output where possible. |

### 12.1 Confidentiality

Confidentiality prevents unauthorized parties from accessing readable information.

Encryption protects confidentiality, but authorization and key security remain necessary.

### 12.2 Integrity

Integrity detects unauthorized modification.

AES-GCM provides authenticated encryption, allowing the receiver to detect modified ciphertext or associated data.

### 12.3 Authenticity

Authenticity establishes confidence in the identity of a communicating party or message origin.

TLS certificate validation and digital signatures address different authenticity requirements.

### 12.4 Replay Protection

Encryption does not automatically prevent replay attacks.

A valid encrypted message may be captured and transmitted again.

Applications handling transactions should use additional controls such as:

- Unique transaction identifiers.
- Sequence numbers.
- Timestamps.
- Expiration limits.
- Replay detection.
- Idempotency rules.

### 12.5 Side-Channel Protection

Cryptographic implementations must also consider information leakage through:

- Timing differences.
- Memory access patterns.
- Error behavior.
- Power consumption.
- Cache behavior.
- Sensitive memory exposure.

Using an established cryptographic implementation is preferable to writing cryptographic primitives from scratch.

---

## 13. Performance and Design Considerations

| Mechanism | Performance characteristics | Suitable workload |
|---|---|---|
| AES-256-GCM | Efficient authenticated encryption | Large files, databases, backups |
| RSA-OAEP | Higher computational cost and limited plaintext size | Small messages and key wrapping |
| RSA-PSS | Signature generation and verification | Signed records and transactions |
| Hybrid encryption | Symmetric data encryption with asymmetric key protection | Large confidential data exchange |
| TLS | Session-based transport protection | Network communication |

### 13.1 Large Files

Large files should generally be encrypted using a streaming or chunked authenticated-encryption design rather than loading the entire file into memory.

Chunked designs must provide appropriate authentication, ordering, truncation detection, and nonce management.

The Python and JavaScript examples demonstrate whole-file encryption and are intended for reasonably sized files.

### 13.2 Key Separation

Separate keys should be used for different cryptographic purposes.

For example:

- Storage encryption.
- Transport key establishment.
- Digital signing.
- Backup encryption.
- Key wrapping.

A key should not be reused across unrelated cryptographic protocols.

### 13.3 Key Recovery

Key loss can make encrypted data permanently inaccessible.

A production system needs:

- Protected key backups.
- Recovery authorization.
- Separation of duties.
- Tested recovery procedures.
- Key-version tracking.
- Documented retention requirements.

### 13.4 Logging

Logs should record security-relevant metadata without exposing:

- Plaintext.
- Raw symmetric keys.
- Private keys.
- Passwords.
- Authentication secrets.
- Sensitive decrypted payloads.

---

## 14. Implementation Limitations

The implementations are executable learning examples, not complete enterprise cryptographic platforms.

| Implementation | Limitation |
|---|---|
| Python | Uses an in-memory key manager and whole-file processing. |
| JavaScript | Uses an in-memory key vault and whole-file processing. |
| C++17 | Implements policy and envelope validation, not actual cryptographic primitives. |
| Java 17 | Demonstrates JCA operations and in-memory key management. |
| PostgreSQL | Stores security metadata and does not independently encrypt application resources. |

Additional considerations:

- The Python implementation requires the `cryptography` dependency.
- The JavaScript implementation requires Node.js with built-in cryptographic support.
- The C++17 implementation compiles without external libraries because it does not claim to implement cryptographic encryption.
- The Java implementation requires a Java 17 runtime with the required cryptographic algorithms available.
- The PostgreSQL implementation uses `pgcrypto` for database cryptographic capabilities, but its principal workflow is based on metadata and policy enforcement.
- Production deployments require persistent and access-controlled key management.
- Real transport encryption requires actual network connections using validated TLS configurations.
- The sample key-management systems do not implement enterprise backup, hardware protection, distributed access control, or disaster recovery.
- File encryption examples do not replace full storage encryption or secure backup management.

---

## 15. Execution and Validation

| File | Runtime | Execution |
|---|---|---|
| Python | Python 3 | `python encryption_fundamentals.py` |
| JavaScript | Node.js 20+ | `node encryption_fundamentals.js` |
| C++17 | GCC or compatible compiler | `g++ -std=c++17 -Wall -Wextra -pedantic encryption.cpp -o encryption` |
| Java 17 | JDK 17 | `javac EncryptionFundamentals.java` followed by `java EncryptionFundamentals` |
| PostgreSQL | PostgreSQL 15+ | Execute the SQL script in a dedicated development database. |

### Validation Scenarios

The implementations demonstrate:

- Successful AES-GCM encryption and decryption.
- Successful RSA-OAEP encryption and decryption.
- RSA-PSS signature verification.
- Hybrid encryption and recovery.
- Rejection of modified ciphertext.
- Key creation and rotation.
- Revoked-key rejection.
- Encrypted-file storage and restoration.
- TLS security configuration.
- Encryption policy evaluation.
- Invalid encryption configuration rejection.
- Database lifecycle auditing.
- Transport compliance reporting.
- Transactional key rotation.

The test scenarios distinguish successful cryptographic operations from policy eligibility and database governance. A successful encryption operation does not by itself establish that the overall application satisfies every security requirement.
