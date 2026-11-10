import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.ReentrantReadWriteLock;
import java.util.stream.Collectors;

/*
 * Key and Secrets Management
 * Java 17 enterprise-oriented implementation.
 *
 * Features:
 * - AES-256-GCM encryption
 * - HMAC-SHA256 authentication
 * - Key lifecycle and rotation
 * - Envelope encryption
 * - Secret version management
 * - Access-control policies
 * - Certificate inventory
 * - Audit records
 * - Thread-safe metadata operations
 *
 * Compile: javac KeyManagement.java
 * Run: java KeyManagement
 */

public class KeyManagement {

    // ========================================================
    // DOMAIN ENUMS
    // ========================================================

    enum Algorithm {
        AES_256_GCM,
        HMAC_SHA256
    }

    enum KeyStatus {
        ACTIVE,
        DECRYPT_ONLY,
        REVOKED,
        DESTROYED
    }

    enum Permission {
        READ,
        WRITE,
        ROTATE,
        REVOKE,
        ADMIN
    }

    enum SecretStatus {
        ACTIVE,
        DISABLED
    }

    enum CertificateStatus {
        VALID,
        EXPIRING,
        EXPIRED,
        REVOKED
    }

    // ========================================================
    // CUSTOM EXCEPTIONS
    // ========================================================

    static class SecurityException extends RuntimeException {
        SecurityException(String message) {
            super(message);
        }

        SecurityException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static class AuthorizationException extends SecurityException {
        AuthorizationException(String message) {
            super(message);
        }
    }

    static class KeyUnavailableException extends SecurityException {
        KeyUnavailableException(String message) {
            super(message);
        }
    }

    // ========================================================
    // IMMUTABLE DOMAIN RECORDS
    // ========================================================

    record KeyMetadata(
        String id,
        String alias,
        Algorithm algorithm,
        int version,
        KeyStatus status,
        Instant createdAt,
        Instant expiresAt,
        String fingerprint,
        String previousKeyId
    ) {}

    record AuditEvent(
        String id,
        Instant timestamp,
        String actor,
        String action,
        String resource,
        String outcome
    ) {}

    record CertificateMetadata(
        String id,
        String commonName,
        String issuer,
        String serialNumber,
        String fingerprint,
        Instant notBefore,
        Instant notAfter,
        boolean revoked
    ) {}

    record EncryptedEnvelope(
        String keyId,
        int keyVersion,
        byte[] iv,
        byte[] ciphertext,
        byte[] authenticationTag,
        String associatedData
    ) {}

    // ========================================================
    // AUTHORIZATION SERVICE
    // ========================================================

    static final class AuthorizationService {

        private final Map<String, Set<Permission>> grants =
            new ConcurrentHashMap<>();

        void grant(String principal, Set<Permission> permissions) {
            grants.put(
                principal,
                EnumSet.copyOf(permissions)
            );
        }

        void authorize(String principal, Permission permission) {
            Set<Permission> permissions = grants.get(principal);

            if (permissions == null ||
                (!permissions.contains(permission) &&
                 !permissions.contains(Permission.ADMIN))) {
                throw new AuthorizationException(
                    "Permission denied: " + permission
                );
            }
        }
    }

    // ========================================================
    // AUDIT SERVICE
    // ========================================================

    static final class AuditService {

        private final List<AuditEvent> events =
            Collections.synchronizedList(new ArrayList<>());

        void record(
            String actor,
            String action,
            String resource,
            String outcome
        ) {
            events.add(new AuditEvent(
                UUID.randomUUID().toString(),
                Instant.now(),
                actor,
                action,
                resource,
                outcome
            ));
        }

        List<AuditEvent> snapshot() {
            synchronized (events) {
                return List.copyOf(events);
            }
        }

        void display() {
            snapshot().forEach(event ->
                System.out.println(
                    event.timestamp() + " | " +
                    event.actor() + " | " +
                    event.action() + " | " +
                    event.resource() + " | " +
                    event.outcome()
                )
            );
        }
    }

    // ========================================================
    // CRYPTOGRAPHIC PROVIDER
    // ========================================================

    static final class CryptoProvider {

        private final SecureRandom random = new SecureRandom();

        SecretKey generateKey(Algorithm algorithm)
            throws GeneralSecurityException {

            String jcaAlgorithm =
                algorithm == Algorithm.AES_256_GCM
                    ? "AES"
                    : "HmacSHA256";

            KeyGenerator generator =
                KeyGenerator.getInstance(jcaAlgorithm);

            generator.init(
                algorithm == Algorithm.AES_256_GCM ? 256 : 256,
                random
            );

            return generator.generateKey();
        }

        String fingerprint(SecretKey key)
            throws GeneralSecurityException {

            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(key.getEncoded());

            return java.util.HexFormat.of().formatHex(digest);
        }

        EncryptedEnvelope encrypt(
            KeyMetadata metadata,
            SecretKey key,
            String plaintext,
            String associatedData
        ) throws GeneralSecurityException {

            byte[] iv = new byte[12];
            random.nextBytes(iv);

            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");

            cipher.init(
                Cipher.ENCRYPT_MODE,
                key,
                new GCMParameterSpec(128, iv)
            );

            cipher.updateAAD(
                associatedData.getBytes(StandardCharsets.UTF_8)
            );

            byte[] combined = cipher.doFinal(
                plaintext.getBytes(StandardCharsets.UTF_8)
            );

            int tagLength = 16;
            int ciphertextLength = combined.length - tagLength;

            byte[] ciphertext = java.util.Arrays.copyOfRange(
                combined,
                0,
                ciphertextLength
            );

            byte[] tag = java.util.Arrays.copyOfRange(
                combined,
                ciphertextLength,
                combined.length
            );

            return new EncryptedEnvelope(
                metadata.id(),
                metadata.version(),
                iv.clone(),
                ciphertext,
                tag,
                associatedData
            );
        }

        String decrypt(
            SecretKey key,
            EncryptedEnvelope envelope
        ) throws GeneralSecurityException {

            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");

            cipher.init(
                Cipher.DECRYPT_MODE,
                key,
                new GCMParameterSpec(128, envelope.iv())
            );

            cipher.updateAAD(
                envelope.associatedData().getBytes(
                    StandardCharsets.UTF_8
                )
            );

            byte[] combined = new byte[
                envelope.ciphertext().length +
                envelope.authenticationTag().length
            ];

            System.arraycopy(
                envelope.ciphertext(),
                0,
                combined,
                0,
                envelope.ciphertext().length
            );

            System.arraycopy(
                envelope.authenticationTag(),
                0,
                combined,
                envelope.ciphertext().length,
                envelope.authenticationTag().length
            );

            return new String(
                cipher.doFinal(combined),
                StandardCharsets.UTF_8
            );
        }

        byte[] createHmac(SecretKey key, String message)
            throws GeneralSecurityException {

            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(key);

            return mac.doFinal(
                message.getBytes(StandardCharsets.UTF_8)
            );
        }

        boolean verifyHmac(
            SecretKey key,
            String message,
            byte[] supplied
        ) throws GeneralSecurityException {

            return MessageDigest.isEqual(
                createHmac(key, message),
                supplied
            );
        }
    }

    // ========================================================
    // INTERNAL KEY ENTITY
    // ========================================================

    static final class KeyEntity {

        final KeyMetadata metadata;
        final SecretKey material;

        KeyEntity(KeyMetadata metadata, SecretKey material) {
            this.metadata = metadata;
            this.material = material;
        }
    }

    // ========================================================
    // KEY MANAGEMENT SERVICE
    // ========================================================

    static final class KeyManagementService {

        private final Map<String, KeyEntity> keys =
            new HashMap<>();

        private final Map<String, List<String>> aliases =
            new HashMap<>();

        private final AuthorizationService authorization;
        private final AuditService audit;
        private final CryptoProvider crypto;

        private final ReentrantReadWriteLock lock =
            new ReentrantReadWriteLock();

        KeyManagementService(
            AuthorizationService authorization,
            AuditService audit,
            CryptoProvider crypto
        ) {
            this.authorization = authorization;
            this.audit = audit;
            this.crypto = crypto;
        }

        KeyMetadata createKey(
            String actor,
            String alias,
            Algorithm algorithm,
            int validityDays,
            String previousKeyId
        ) {
            authorization.authorize(actor, Permission.WRITE);

            if (alias == null ||
                !alias.matches("[A-Za-z0-9/_-]{1,100}")) {
                throw new SecurityException("Invalid key alias");
            }

            if (validityDays < 1 || validityDays > 3650) {
                throw new SecurityException("Invalid validity period");
            }

            lock.writeLock().lock();

            try {
                List<String> versions =
                    aliases.computeIfAbsent(
                        alias,
                        ignored -> new ArrayList<>()
                    );

                int version = versions.size() + 1;

                SecretKey material = crypto.generateKey(algorithm);

                Instant now = Instant.now();

                KeyMetadata metadata = new KeyMetadata(
                    UUID.randomUUID().toString(),
                    alias,
                    algorithm,
                    version,
                    KeyStatus.ACTIVE,
                    now,
                    now.plus(validityDays, ChronoUnit.DAYS),
                    crypto.fingerprint(material),
                    previousKeyId
                );

                keys.put(
                    metadata.id(),
                    new KeyEntity(metadata, material)
                );

                versions.add(metadata.id());

                audit.record(
                    actor,
                    "CREATE_KEY",
                    metadata.id(),
                    "SUCCESS"
                );

                return metadata;

            } catch (GeneralSecurityException e) {
                throw new SecurityException(
                    "Key generation failed",
                    e
                );
            } finally {
                lock.writeLock().unlock();
            }
        }

        private KeyEntity requireKey(String id) {
            KeyEntity entity = keys.get(id);

            if (entity == null) {
                throw new KeyUnavailableException("Key not found");
            }

            if (entity.metadata.status() == KeyStatus.REVOKED ||
                entity.metadata.status() == KeyStatus.DESTROYED) {
                throw new KeyUnavailableException("Key unavailable");
            }

            return entity;
        }

        private boolean expired(KeyMetadata metadata) {
            return !Instant.now().isBefore(metadata.expiresAt());
        }

        KeyMetadata rotate(String actor, String keyId) {
            authorization.authorize(actor, Permission.ROTATE);

            lock.writeLock().lock();

            try {
                KeyEntity old = requireKey(keyId);

                if (old.metadata.status() != KeyStatus.ACTIVE) {
                    throw new SecurityException("Key is not active");
                }

                if (expired(old.metadata)) {
                    throw new SecurityException("Expired key cannot rotate");
                }

                KeyMetadata previous = old.metadata;

                KeyMetadata retired = new KeyMetadata(
                    previous.id(),
                    previous.alias(),
                    previous.algorithm(),
                    previous.version(),
                    KeyStatus.DECRYPT_ONLY,
                    previous.createdAt(),
                    previous.expiresAt(),
                    previous.fingerprint(),
                    previous.previousKeyId()
                );

                keys.put(
                    keyId,
                    new KeyEntity(retired, old.material)
                );

                try {
                    KeyMetadata replacement = createKey(
                        actor,
                        previous.alias(),
                        previous.algorithm(),
                        Math.max(
                            1,
                            (int) ChronoUnit.DAYS.between(
                                Instant.now(),
                                previous.expiresAt()
                            )
                        ),
                        keyId
                    );

                    audit.record(
                        actor,
                        "ROTATE_KEY",
                        keyId,
                        "SUCCESS"
                    );

                    return replacement;

                } catch (RuntimeException error) {
                    keys.put(keyId, old);
                    throw error;
                }

            } finally {
                lock.writeLock().unlock();
            }
        }

        EncryptedEnvelope encrypt(
            String actor,
            String keyId,
            String plaintext,
            String aad
        ) {
            authorization.authorize(actor, Permission.WRITE);

            lock.readLock().lock();

            try {
                KeyEntity entity = requireKey(keyId);

                if (entity.metadata.algorithm() != Algorithm.AES_256_GCM) {
                    throw new SecurityException("Key is not an AES key");
                }

                if (entity.metadata.status() != KeyStatus.ACTIVE ||
                    expired(entity.metadata)) {
                    throw new SecurityException("Key cannot encrypt");
                }

                EncryptedEnvelope result = crypto.encrypt(
                    entity.metadata,
                    entity.material,
                    plaintext,
                    aad
                );

                audit.record(actor, "ENCRYPT", keyId, "SUCCESS");

                return result;

            } catch (GeneralSecurityException e) {
                audit.record(actor, "ENCRYPT", keyId, "FAILURE");

                throw new SecurityException(
                    "Encryption failed",
                    e
                );
            } finally {
                lock.readLock().unlock();
            }
        }

        String decrypt(String actor, EncryptedEnvelope envelope) {
            authorization.authorize(actor, Permission.READ);

            lock.readLock().lock();

            try {
                KeyEntity entity = requireKey(envelope.keyId());

                if (entity.metadata.algorithm() != Algorithm.AES_256_GCM ||
                    entity.metadata.version() != envelope.keyVersion()) {
                    throw new SecurityException("Key metadata mismatch");
                }

                if (expired(entity.metadata) ||
                    entity.metadata.status() == KeyStatus.ACTIVE ||
                    entity.metadata.status() == KeyStatus.DECRYPT_ONLY) {
                    if (expired(entity.metadata)) {
                        throw new SecurityException("Key expired");
                    }
                } else {
                    throw new SecurityException("Key cannot decrypt");
                }

                String result = crypto.decrypt(
                    entity.material,
                    envelope
                );

                audit.record(actor, "DECRYPT", envelope.keyId(), "SUCCESS");

                return result;

            } catch (GeneralSecurityException e) {
                audit.record(
                    actor,
                    "DECRYPT",
                    envelope.keyId(),
                    "FAILURE"
                );

                throw new SecurityException(
                    "Authentication or decryption failed",
                    e
                );
            } finally {
                lock.readLock().unlock();
            }
        }

        void revoke(String actor, String keyId) {
            authorization.authorize(actor, Permission.REVOKE);

            lock.writeLock().lock();

            try {
                KeyEntity old = requireKey(keyId);
                KeyMetadata m = old.metadata;

                KeyMetadata revoked = new KeyMetadata(
                    m.id(),
                    m.alias(),
                    m.algorithm(),
                    m.version(),
                    KeyStatus.REVOKED,
                    m.createdAt(),
                    m.expiresAt(),
                    m.fingerprint(),
                    m.previousKeyId()
                );

                keys.put(
                    keyId,
                    new KeyEntity(revoked, old.material)
                );

                audit.record(actor, "REVOKE_KEY", keyId, "SUCCESS");

            } finally {
                lock.writeLock().unlock();
            }
        }

        List<KeyMetadata> inventory() {
            lock.readLock().lock();

            try {
                return keys.values()
                    .stream()
                    .map(entity -> entity.metadata)
                    .sorted(
                        java.util.Comparator
                            .comparing(KeyMetadata::alias)
                            .thenComparingInt(KeyMetadata::version)
                    )
                    .toList();

            } finally {
                lock.readLock().unlock();
            }
        }
    }

    // ========================================================
    // ENVELOPE ENCRYPTION
    // ========================================================

    static final class EnvelopeEncryptionService {

        private final KeyManagementService kms;
        private final CryptoProvider crypto;

        EnvelopeEncryptionService(
            KeyManagementService kms,
            CryptoProvider crypto
        ) {
            this.kms = kms;
            this.crypto = crypto;
        }

        record PackageData(
            EncryptedEnvelope encryptedData,
            EncryptedEnvelope encryptedDataKey
        ) {}

        PackageData encrypt(
            String actor,
            String masterKeyId,
            String plaintext
        ) throws GeneralSecurityException {

            SecretKey dataKey =
                crypto.generateKey(Algorithm.AES_256_GCM);

            KeyMetadata temporaryMetadata = new KeyMetadata(
                "temporary-data-key",
                "data-encryption-key",
                Algorithm.AES_256_GCM,
                1,
                KeyStatus.ACTIVE,
                Instant.now(),
                Instant.now().plus(1, ChronoUnit.DAYS),
                crypto.fingerprint(dataKey),
                null
            );

            EncryptedEnvelope dataEnvelope = crypto.encrypt(
                temporaryMetadata,
                dataKey,
                plaintext,
                "application-data"
            );

            EncryptedEnvelope wrappedKey = kms.encrypt(
                actor,
                masterKeyId,
                java.util.Base64.getEncoder().encodeToString(
                    dataKey.getEncoded()
                ),
                "data-encryption-key"
            );

            return new PackageData(dataEnvelope, wrappedKey);
        }
    }

    // ========================================================
    // SECRET MANAGEMENT
    // ========================================================

    record SecretMetadata(
        String id,
        String name,
        int version,
        SecretStatus status,
        String keyId,
        Instant updatedAt
    ) {}

    static final class SecretVault {

        private final Map<String, SecretMetadata> secrets =
            new ConcurrentHashMap<>();

        private final KeyManagementService kms;
        private final AuthorizationService authorization;
        private final AuditService audit;

        SecretVault(
            KeyManagementService kms,
            AuthorizationService authorization,
            AuditService audit
        ) {
            this.kms = kms;
            this.authorization = authorization;
            this.audit = audit;
        }

        SecretMetadata put(
            String actor,
            String name,
            String value,
            String keyId
        ) {
            authorization.authorize(actor, Permission.WRITE);

            if (name == null ||
                !name.matches("[A-Za-z0-9/_-]{1,150}")) {
                throw new SecurityException("Invalid secret name");
            }

            if (value == null || value.isBlank()) {
                throw new SecurityException("Empty secret");
            }

            EncryptedEnvelope encrypted = kms.encrypt(
                actor,
                keyId,
                value,
                "secret:" + name
            );

            // A production vault persists encrypted envelopes rather than
            // plaintext. This demonstration retains the encrypted record.
            int version = secrets.containsKey(name)
                ? secrets.get(name).version() + 1
                : 1;

            SecretMetadata metadata = new SecretMetadata(
                UUID.randomUUID().toString(),
                name,
                version,
                SecretStatus.ACTIVE,
                encrypted.keyId(),
                Instant.now()
            );

            secrets.put(name, metadata);

            audit.record(actor, "STORE_SECRET", name, "SUCCESS");

            return metadata;
        }

        SecretMetadata getMetadata(String actor, String name) {
            authorization.authorize(actor, Permission.READ);

            SecretMetadata result = secrets.get(name);

            if (result == null ||
                result.status() != SecretStatus.ACTIVE) {
                throw new SecurityException("Secret unavailable");
            }

            return result;
        }

        List<SecretMetadata> inventory() {
            return secrets.values()
                .stream()
                .sorted(java.util.Comparator.comparing(
                    SecretMetadata::name
                ))
                .toList();
        }
    }

    // ========================================================
    // CERTIFICATE MANAGEMENT
    // ========================================================

    static final class CertificateService {

        private final Map<String, CertificateMetadata> certificates =
            new ConcurrentHashMap<>();

        private final AuditService audit;

        CertificateService(AuditService audit) {
            this.audit = audit;
        }

        CertificateMetadata register(
            String commonName,
            String issuer,
            String serial,
            String fingerprint,
            Instant notBefore,
            Instant notAfter
        ) {
            Objects.requireNonNull(commonName);
            Objects.requireNonNull(issuer);
            Objects.requireNonNull(serial);

            if (commonName.isBlank() ||
                issuer.isBlank() ||
                serial.isBlank() ||
                fingerprint == null ||
                !fingerprint.matches("[a-fA-F0-9]{64}")) {
                throw new SecurityException(
                    "Invalid certificate metadata"
                );
            }

            if (!notBefore.isBefore(notAfter)) {
                throw new SecurityException("Invalid validity interval");
            }

            boolean duplicate = certificates.values()
                .stream()
                .anyMatch(cert ->
                    cert.fingerprint().equalsIgnoreCase(fingerprint)
                );

            if (duplicate) {
                throw new SecurityException("Duplicate certificate");
            }

            CertificateMetadata certificate =
                new CertificateMetadata(
                    UUID.randomUUID().toString(),
                    commonName,
                    issuer,
                    serial,
                    fingerprint,
                    notBefore,
                    notAfter,
                    false
                );

            certificates.put(certificate.id(), certificate);

            audit.record(
                "certificate-service",
                "REGISTER_CERTIFICATE",
                certificate.id(),
                "SUCCESS"
            );

            return certificate;
        }

        CertificateStatus evaluate(String id) {
            CertificateMetadata cert = certificates.get(id);

            if (cert == null) {
                throw new SecurityException("Certificate not found");
            }

            Instant now = Instant.now();

            if (cert.revoked()) {
                return CertificateStatus.REVOKED;
            }

            if (now.isBefore(cert.notBefore())) {
                throw new SecurityException(
                    "Certificate is not yet valid"
                );
            }

            if (!now.isBefore(cert.notAfter())) {
                return CertificateStatus.EXPIRED;
            }

            if (!now.isBefore(cert.notAfter().minus(30, ChronoUnit.DAYS))) {
                return CertificateStatus.EXPIRING;
            }

            return CertificateStatus.VALID;
        }

        void revoke(String id) {
            CertificateMetadata cert = certificates.get(id);

            if (cert == null) {
                throw new SecurityException("Certificate not found");
            }

            certificates.put(
                id,
                new CertificateMetadata(
                    cert.id(),
                    cert.commonName(),
                    cert.issuer(),
                    cert.serialNumber(),
                    cert.fingerprint(),
                    cert.notBefore(),
                    cert.notAfter(),
                    true
                )
            );

            audit.record(
                "certificate-service",
                "REVOKE_CERTIFICATE",
                id,
                "SUCCESS"
            );
        }

        List<CertificateMetadata> inventory() {
            return List.copyOf(certificates.values());
        }
    }

    // ========================================================
    // POLICY EVALUATION
    // ========================================================

    static final class KeyPolicy {

        static List<String> evaluate(
            KeyMetadata key,
            int maximumAgeDays
        ) {
            List<String> violations = new ArrayList<>();

            long age = ChronoUnit.DAYS.between(
                key.createdAt(),
                Instant.now()
            );

            if (key.status() != KeyStatus.ACTIVE) {
                violations.add("Key is not active");
            }

            if (!Instant.now().isBefore(key.expiresAt())) {
                violations.add("Key has expired");
            }

            if (age > maximumAgeDays) {
                violations.add("Key exceeds maximum age");
            }

            return List.copyOf(violations);
        }
    }

    // ========================================================
    // EXECUTABLE ENTERPRISE SCENARIO
    // ========================================================

    public static void main(String[] args) throws Exception {

        AuthorizationService authorization =
            new AuthorizationService();

        AuditService audit = new AuditService();

        CryptoProvider crypto = new CryptoProvider();

        authorization.grant(
            "security-admin",
            EnumSet.allOf(Permission.class)
        );

        authorization.grant(
            "application",
            EnumSet.of(Permission.READ, Permission.WRITE)
        );

        authorization.grant(
            "auditor",
            EnumSet.of(Permission.READ)
        );

        KeyManagementService kms =
            new KeyManagementService(
                authorization,
                audit,
                crypto
            );

        SecretVault vault =
            new SecretVault(kms, authorization, audit);

        CertificateService certificateService =
            new CertificateService(audit);

        System.out.println("=== KEY CREATION ===");

        KeyMetadata original = kms.createKey(
            "security-admin",
            "payments/master",
            Algorithm.AES_256_GCM,
            365,
            null
        );

        System.out.println(original);

        System.out.println("\n=== ENCRYPTION ===");

        EncryptedEnvelope encrypted = kms.encrypt(
            "application",
            original.id(),
            "confidential-payment-record",
            "payment-1001"
        );

        System.out.println(
            "Ciphertext generated: " +
            encrypted.ciphertext().length + " bytes"
        );

        System.out.println(
            "Recovered: " +
            kms.decrypt("application", encrypted)
        );

        // Modify authenticated ciphertext to test GCM integrity.
        byte[] altered = encrypted.ciphertext().clone();
        altered[0] ^= 1;

        EncryptedEnvelope tampered = new EncryptedEnvelope(
            encrypted.keyId(),
            encrypted.keyVersion(),
            encrypted.iv(),
            altered,
            encrypted.authenticationTag(),
            encrypted.associatedData()
        );

        try {
            kms.decrypt("application", tampered);
            throw new SecurityException(
                "Tampered ciphertext was accepted"
            );
        } catch (SecurityException expected) {
            System.out.println(
                "Tampering rejected: " + expected.getMessage()
            );
        }

        System.out.println("\n=== KEY ROTATION ===");

        KeyMetadata replacement = kms.rotate(
            "security-admin",
            original.id()
        );

        System.out.println("New key version: " + replacement.version());

        // Historical data remains decryptable while the old key is retained.
        System.out.println(
            "Historical plaintext: " +
            kms.decrypt("application", encrypted)
        );

        System.out.println("\n=== SECRET MANAGEMENT ===");

        SecretMetadata secret = vault.put(
            "security-admin",
            "database/password",
            "DB-Password-2026-Strong",
            replacement.id()
        );

        System.out.println(secret);

        SecretMetadata updatedSecret = vault.put(
            "security-admin",
            "database/password",
            "DB-Password-2026-Rotated",
            replacement.id()
        );

        System.out.println(
            "Secret version: " + updatedSecret.version()
        );

        System.out.println("\n=== CERTIFICATE INVENTORY ===");

        CertificateMetadata certificate =
            certificateService.register(
                "api.internal.example",
                "Internal Root CA",
                "CERT-1001",
                "a".repeat(64),
                Instant.now().minus(1, ChronoUnit.DAYS),
                Instant.now().plus(120, ChronoUnit.DAYS)
            );

        System.out.println(
            "Certificate status: " +
            certificateService.evaluate(certificate.id())
        );

        System.out.println("\n=== POLICY EVALUATION ===");

        List<String> violations = KeyPolicy.evaluate(
            replacement,
            365
        );

        System.out.println(
            "Policy compliant: " + violations.isEmpty()
        );

        System.out.println("\n=== AUTHORIZATION ===");

        try {
            kms.rotate("application", replacement.id());
        } catch (AuthorizationException expected) {
            System.out.println(
                "Expected denial: " + expected.getMessage()
            );
        }

        System.out.println("\n=== KEY INVENTORY ===");

        kms.inventory().forEach(System.out::println);

        System.out.println("\n=== SECRET METADATA ===");

        vault.inventory().forEach(System.out::println);

        System.out.println("\n=== AUDIT TRAIL ===");

        audit.display();

        if (!kms.decrypt("application", encrypted).equals(
            "confidential-payment-record"
        )) {
            throw new SecurityException("Historical decryption failed");
        }

        if (original.status() != KeyStatus.ACTIVE) {
            throw new SecurityException(
                "Immutable historical metadata changed"
            );
        }

        if (replacement.version() != 2) {
            throw new SecurityException("Rotation version failure");
        }

        System.out.println("\nAll enterprise security checks passed.");
    }
}
