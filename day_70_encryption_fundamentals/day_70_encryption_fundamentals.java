import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;
import javax.crypto.spec.SecretKeySpec;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.MGF1ParameterSpec;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/*
 * Encryption Fundamentals: Java 17
 *
 * Enterprise encryption architecture.
 *
 * Demonstrates:
 * - AES-256-GCM symmetric encryption.
 * - RSA-OAEP asymmetric encryption.
 * - Hybrid envelope encryption.
 * - Encryption at rest.
 * - Encryption in transit policy.
 * - Digital signatures.
 * - Key lifecycle and rotation.
 * - Policy evaluation.
 * - State transitions.
 *
 * No third-party dependencies.
 *
 * Compile:
 * javac EncryptionFundamentals.java
 *
 * Run:
 * java EncryptionFundamentals
 */

public class EncryptionFundamentals {

    private static final SecureRandom RANDOM = new SecureRandom();

    private static final String AES_ALGORITHM = "AES/GCM/NoPadding";

    private static final String RSA_TRANSFORMATION =
            "RSA/ECB/OAEPPadding";

    private static final int AES_KEY_BITS = 256;
    private static final int GCM_NONCE_BYTES = 12;
    private static final int GCM_TAG_BITS = 128;

    enum ProtectionLocation {
        AT_REST,
        IN_TRANSIT
    }

    enum EncryptionType {
        SYMMETRIC,
        ASYMMETRIC,
        HYBRID
    }

    enum KeyStatus {
        ACTIVE,
        RETIRED,
        REVOKED
    }

    enum ReviewDecision {
        ALLOW,
        DENY
    }

    static class EncryptionException extends Exception {
        EncryptionException(String message) {
            super(message);
        }

        EncryptionException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static class PolicyViolationException extends Exception {
        PolicyViolationException(String message) {
            super(message);
        }
    }

    record EncryptionResult(
            byte[] nonce,
            byte[] ciphertext,
            byte[] authenticationTag,
            String algorithm
    ) {
        EncryptionResult {
            nonce = nonce.clone();
            ciphertext = ciphertext.clone();
            authenticationTag = authenticationTag.clone();
        }

        @Override
        public byte[] nonce() {
            return nonce.clone();
        }

        @Override
        public byte[] ciphertext() {
            return ciphertext.clone();
        }

        @Override
        public byte[] authenticationTag() {
            return authenticationTag.clone();
        }
    }

    record KeyMetadata(
            String keyId,
            String algorithm,
            int strengthBits,
            Instant createdAt,
            KeyStatus status
    ) {}

    record EncryptionPolicy(
            String policyId,
            ProtectionLocation location,
            EncryptionType requiredType,
            int minimumKeyBits,
            boolean authenticationRequired,
            boolean certificateValidationRequired,
            boolean uniqueNonceRequired
    ) {
        EncryptionPolicy {
            Objects.requireNonNull(policyId);
            Objects.requireNonNull(location);
            Objects.requireNonNull(requiredType);

            if (policyId.isBlank() || minimumKeyBits <= 0) {
                throw new IllegalArgumentException("Invalid policy");
            }
        }
    }

    record EncryptionRequest(
            String resourceId,
            ProtectionLocation location,
            EncryptionType type,
            String algorithm,
            String keyId,
            int keyBits,
            boolean authenticated,
            boolean uniqueNonce,
            boolean certificateValidated
    ) {}

    record PolicyResult(
            ReviewDecision decision,
            List<String> reasons
    ) {
        PolicyResult {
            reasons = List.copyOf(reasons);
        }
    }

    record HybridEnvelope(
            int version,
            String algorithm,
            byte[] wrappedKey,
            byte[] nonce,
            byte[] ciphertext,
            byte[] tag
    ) {
        HybridEnvelope {
            wrappedKey = wrappedKey.clone();
            nonce = nonce.clone();
            ciphertext = ciphertext.clone();
            tag = tag.clone();
        }

        @Override
        public byte[] wrappedKey() {
            return wrappedKey.clone();
        }

        @Override
        public byte[] nonce() {
            return nonce.clone();
        }

        @Override
        public byte[] ciphertext() {
            return ciphertext.clone();
        }

        @Override
        public byte[] tag() {
            return tag.clone();
        }
    }

    interface EncryptionService {
        EncryptionResult encrypt(
                byte[] plaintext,
                SecretKey key,
                byte[] associatedData
        ) throws GeneralSecurityException;

        byte[] decrypt(
                EncryptionResult encrypted,
                SecretKey key,
                byte[] associatedData
        ) throws GeneralSecurityException;
    }

    static class AESGCMService implements EncryptionService {

        @Override
        public EncryptionResult encrypt(
                byte[] plaintext,
                SecretKey key,
                byte[] associatedData
        ) throws GeneralSecurityException {

            validateAESKey(key);

            byte[] nonce = new byte[GCM_NONCE_BYTES];
            RANDOM.nextBytes(nonce);

            Cipher cipher = Cipher.getInstance(AES_ALGORITHM);

            cipher.init(
                    Cipher.ENCRYPT_MODE,
                    key,
                    new GCMParameterSpec(GCM_TAG_BITS, nonce)
            );

            if (associatedData != null) {
                cipher.updateAAD(associatedData);
            }

            byte[] combined = cipher.doFinal(plaintext);

            int tagLength = GCM_TAG_BITS / 8;
            int ciphertextLength = combined.length - tagLength;

            byte[] ciphertext = new byte[ciphertextLength];
            byte[] tag = new byte[tagLength];

            System.arraycopy(
                    combined, 0,
                    ciphertext, 0,
                    ciphertextLength
            );

            System.arraycopy(
                    combined, ciphertextLength,
                    tag, 0,
                    tagLength
            );

            return new EncryptionResult(
                    nonce,
                    ciphertext,
                    tag,
                    "AES-256-GCM"
            );
        }

        @Override
        public byte[] decrypt(
                EncryptionResult encrypted,
                SecretKey key,
                byte[] associatedData
        ) throws GeneralSecurityException {

            validateAESKey(key);

            if (encrypted.nonce().length != GCM_NONCE_BYTES ||
                    encrypted.authenticationTag().length != 16) {
                throw new GeneralSecurityException(
                        "Invalid GCM nonce or tag"
                );
            }

            Cipher cipher = Cipher.getInstance(AES_ALGORITHM);

            cipher.init(
                    Cipher.DECRYPT_MODE,
                    key,
                    new GCMParameterSpec(
                            GCM_TAG_BITS,
                            encrypted.nonce()
                    )
            );

            if (associatedData != null) {
                cipher.updateAAD(associatedData);
            }

            byte[] combined = new byte[
                    encrypted.ciphertext().length +
                    encrypted.authenticationTag().length
            ];

            System.arraycopy(
                    encrypted.ciphertext(),
                    0,
                    combined,
                    0,
                    encrypted.ciphertext().length
            );

            System.arraycopy(
                    encrypted.authenticationTag(),
                    0,
                    combined,
                    encrypted.ciphertext().length,
                    encrypted.authenticationTag().length
            );

            return cipher.doFinal(combined);
        }

        private static void validateAESKey(SecretKey key)
                throws GeneralSecurityException {

            if (key == null ||
                    !"AES".equalsIgnoreCase(key.getAlgorithm()) ||
                    key.getEncoded() == null ||
                    key.getEncoded().length != 32) {
                throw new GeneralSecurityException(
                        "A valid AES-256 key is required"
                );
            }
        }
    }

    static class RSAService {

        private final KeyPair keyPair;

        RSAService() throws GeneralSecurityException {
            KeyPairGenerator generator =
                    KeyPairGenerator.getInstance("RSA");

            generator.initialize(3072, RANDOM);
            keyPair = generator.generateKeyPair();
        }

        PublicKey publicKey() {
            return keyPair.getPublic();
        }

        PrivateKey privateKey() {
            return keyPair.getPrivate();
        }

        byte[] encrypt(byte[] plaintext, PublicKey recipient)
                throws GeneralSecurityException {

            Cipher cipher = Cipher.getInstance(RSA_TRANSFORMATION);

            OAEPParameterSpec parameters = new OAEPParameterSpec(
                    "SHA-256",
                    "MGF1",
                    MGF1ParameterSpec.SHA256,
                    PSource.PSpecified.DEFAULT
            );

            cipher.init(
                    Cipher.ENCRYPT_MODE,
                    recipient,
                    parameters
            );

            return cipher.doFinal(plaintext);
        }

        byte[] decrypt(byte[] ciphertext)
                throws GeneralSecurityException {

            Cipher cipher = Cipher.getInstance(RSA_TRANSFORMATION);

            OAEPParameterSpec parameters = new OAEPParameterSpec(
                    "SHA-256",
                    "MGF1",
                    MGF1ParameterSpec.SHA256,
                    PSource.PSpecified.DEFAULT
            );

            cipher.init(
                    Cipher.DECRYPT_MODE,
                    keyPair.getPrivate(),
                    parameters
            );

            return cipher.doFinal(ciphertext);
        }

        byte[] sign(byte[] message)
                throws GeneralSecurityException {

            Signature signature = Signature.getInstance("RSASSA-PSS");

            signature.setParameter(
                    new java.security.spec.PSSParameterSpec(
                            "SHA-256",
                            "MGF1",
                            MGF1ParameterSpec.SHA256,
                            32,
                            1
                    )
            );

            signature.initSign(keyPair.getPrivate(), RANDOM);
            signature.update(message);

            return signature.sign();
        }

        boolean verify(byte[] message, byte[] signed)
                throws GeneralSecurityException {

            Signature signature = Signature.getInstance("RSASSA-PSS");

            signature.setParameter(
                    new java.security.spec.PSSParameterSpec(
                            "SHA-256",
                            "MGF1",
                            MGF1ParameterSpec.SHA256,
                            32,
                            1
                    )
            );

            signature.initVerify(keyPair.getPublic());
            signature.update(message);

            return signature.verify(signed);
        }
    }

    static class HybridEncryptionService {

        private final AESGCMService aes = new AESGCMService();

        HybridEnvelope encrypt(
                byte[] plaintext,
                PublicKey recipient
        ) throws GeneralSecurityException {

            KeyGenerator generator = KeyGenerator.getInstance("AES");
            generator.init(AES_KEY_BITS, RANDOM);

            SecretKey dataKey = generator.generateKey();

            byte[] aad = "hybrid-envelope-v1".getBytes(
                    StandardCharsets.UTF_8
            );

            EncryptionResult result = aes.encrypt(
                    plaintext,
                    dataKey,
                    aad
            );

            RSAService rsa = null;

            Cipher wrappingCipher = Cipher.getInstance(
                    RSA_TRANSFORMATION
            );

            OAEPParameterSpec parameters = new OAEPParameterSpec(
                    "SHA-256",
                    "MGF1",
                    MGF1ParameterSpec.SHA256,
                    PSource.PSpecified.DEFAULT
            );

            wrappingCipher.init(
                    Cipher.ENCRYPT_MODE,
                    recipient,
                    parameters
            );

            byte[] wrappedKey = wrappingCipher.doFinal(
                    dataKey.getEncoded()
            );

            return new HybridEnvelope(
                    1,
                    "AES-256-GCM+RSA-OAEP-SHA256",
                    wrappedKey,
                    result.nonce(),
                    result.ciphertext(),
                    result.authenticationTag()
            );
        }

        byte[] decrypt(
                HybridEnvelope envelope,
                PrivateKey recipientPrivateKey
        ) throws GeneralSecurityException {

            if (envelope.version() != 1 ||
                    !envelope.algorithm().equals(
                            "AES-256-GCM+RSA-OAEP-SHA256")) {
                throw new GeneralSecurityException(
                        "Unsupported envelope"
                );
            }

            Cipher wrappingCipher = Cipher.getInstance(
                    RSA_TRANSFORMATION
            );

            OAEPParameterSpec parameters = new OAEPParameterSpec(
                    "SHA-256",
                    "MGF1",
                    MGF1ParameterSpec.SHA256,
                    PSource.PSpecified.DEFAULT
            );

            wrappingCipher.init(
                    Cipher.DECRYPT_MODE,
                    recipientPrivateKey,
                    parameters
            );

            byte[] rawKey = wrappingCipher.doFinal(
                    envelope.wrappedKey()
            );

            if (rawKey.length != 32) {
                throw new GeneralSecurityException(
                        "Invalid wrapped data key"
                );
            }

            SecretKey dataKey = new SecretKeySpec(rawKey, "AES");

            EncryptionResult result = new EncryptionResult(
                    envelope.nonce(),
                    envelope.ciphertext(),
                    envelope.tag(),
                    "AES-256-GCM"
            );

            return aes.decrypt(
                    result,
                    dataKey,
                    "hybrid-envelope-v1".getBytes(
                            StandardCharsets.UTF_8
                    )
            );
        }
    }

    static class KeyVault {

        private final Map<String, SecretKey> material =
                new HashMap<>();

        private final Map<String, KeyMetadata> metadata =
                new HashMap<>();

        private String activeKeyId;

        synchronized String createKey()
                throws GeneralSecurityException {

            KeyGenerator generator = KeyGenerator.getInstance("AES");
            generator.init(AES_KEY_BITS, RANDOM);

            SecretKey key = generator.generateKey();

            if (activeKeyId != null) {
                KeyMetadata old = metadata.get(activeKeyId);

                metadata.put(
                        activeKeyId,
                        new KeyMetadata(
                                old.keyId(),
                                old.algorithm(),
                                old.strengthBits(),
                                old.createdAt(),
                                KeyStatus.RETIRED
                        )
                );
            }

            String id = UUID.randomUUID().toString();

            material.put(id, key);

            metadata.put(
                    id,
                    new KeyMetadata(
                            id,
                            "AES-256-GCM",
                            256,
                            Instant.now(),
                            KeyStatus.ACTIVE
                    )
            );

            activeKeyId = id;

            return id;
        }

        synchronized SecretKey getKey(String id)
                throws EncryptionException {

            KeyMetadata record = metadata.get(id);

            if (record == null ||
                    record.status() == KeyStatus.REVOKED) {
                throw new EncryptionException(
                        "Key is unavailable"
                );
            }

            return material.get(id);
        }

        synchronized SecretKey getActiveKey()
                throws EncryptionException {

            if (activeKeyId == null) {
                throw new EncryptionException(
                        "No active encryption key"
                );
            }

            return getKey(activeKeyId);
        }

        synchronized void revoke(String id)
                throws EncryptionException {

            KeyMetadata record = metadata.get(id);

            if (record == null) {
                throw new EncryptionException("Unknown key");
            }

            metadata.put(
                    id,
                    new KeyMetadata(
                            record.keyId(),
                            record.algorithm(),
                            record.strengthBits(),
                            record.createdAt(),
                            KeyStatus.REVOKED
                    )
            );

            if (id.equals(activeKeyId)) {
                activeKeyId = null;
            }
        }

        synchronized List<KeyMetadata> inventory() {
            return List.copyOf(metadata.values());
        }
    }

    static class PolicyService {

        private final Map<String, EncryptionPolicy> policies =
                new HashMap<>();

        void register(EncryptionPolicy policy) {
            if (policies.putIfAbsent(
                    policy.policyId(),
                    policy
            ) != null) {
                throw new IllegalArgumentException(
                        "Duplicate policy identifier"
                );
            }
        }

        PolicyResult evaluate(EncryptionRequest request) {

            List<String> reasons = new ArrayList<>();

            EncryptionPolicy policy = policies.values()
                    .stream()
                    .filter(p -> p.location() == request.location())
                    .findFirst()
                    .orElse(null);

            if (policy == null) {
                reasons.add("No matching encryption policy");
            } else {
                if (request.type() != policy.requiredType()) {
                    reasons.add("Encryption type mismatch");
                }

                if (request.keyBits() < policy.minimumKeyBits()) {
                    reasons.add("Key strength below policy minimum");
                }

                if (policy.authenticationRequired() &&
                        !request.authenticated()) {
                    reasons.add("Authentication is mandatory");
                }

                if (policy.uniqueNonceRequired() &&
                        !request.uniqueNonce()) {
                    reasons.add("Nonce uniqueness is required");
                }

                if (policy.certificateValidationRequired() &&
                        !request.certificateValidated()) {
                    reasons.add("Certificate validation failed");
                }
            }

            return new PolicyResult(
                    reasons.isEmpty()
                            ? ReviewDecision.ALLOW
                            : ReviewDecision.DENY,
                    reasons
            );
        }
    }

    static String fingerprint(byte[] data)
            throws GeneralSecurityException {

        return java.util.HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(data)
        );
    }

    static void demonstrate() throws Exception {

        byte[] plaintext = (
                "Confidential enterprise payment record"
        ).getBytes(StandardCharsets.UTF_8);

        System.out.println("ENCRYPTION FUNDAMENTALS");
        System.out.println("======================");

        // AES-GCM.
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(AES_KEY_BITS, RANDOM);

        SecretKey aesKey = generator.generateKey();

        AESGCMService aes = new AESGCMService();

        EncryptionResult encrypted = aes.encrypt(
                plaintext,
                aesKey,
                "enterprise-record-v1".getBytes(
                        StandardCharsets.UTF_8
                )
        );

        byte[] restored = aes.decrypt(
                encrypted,
                aesKey,
                "enterprise-record-v1".getBytes(
                        StandardCharsets.UTF_8
                )
        );

        if (!java.util.Arrays.equals(plaintext, restored)) {
            throw new IllegalStateException("AES verification failed");
        }

        System.out.println("\nAES-256-GCM: PASS");

        // RSA encryption and signatures.
        RSAService rsa = new RSAService();

        byte[] smallMessage = "Key exchange record".getBytes(
                StandardCharsets.UTF_8
        );

        byte[] rsaEncrypted = rsa.encrypt(
                smallMessage,
                rsa.publicKey()
        );

        if (!java.util.Arrays.equals(
                smallMessage,
                rsa.decrypt(rsaEncrypted)
        )) {
            throw new IllegalStateException("RSA verification failed");
        }

        byte[] signature = rsa.sign(plaintext);

        if (!rsa.verify(plaintext, signature)) {
            throw new IllegalStateException("Signature verification failed");
        }

        System.out.println("RSA-OAEP-SHA256: PASS");
        System.out.println("RSA-PSS digital signature: PASS");

        // Hybrid encryption.
        HybridEncryptionService hybrid =
                new HybridEncryptionService();

        HybridEnvelope envelope = hybrid.encrypt(
                plaintext,
                rsa.publicKey()
        );

        byte[] hybridRestored = hybrid.decrypt(
                envelope,
                rsa.privateKey()
        );

        if (!java.util.Arrays.equals(plaintext, hybridRestored)) {
            throw new IllegalStateException(
                    "Hybrid verification failed"
            );
        }

        System.out.println("Hybrid encryption: PASS");

        // Key lifecycle.
        KeyVault vault = new KeyVault();

        String first = vault.createKey();
        String second = vault.createKey();

        if (first.equals(second)) {
            throw new IllegalStateException("Key rotation failed");
        }

        System.out.println("Key rotation: PASS");

        for (KeyMetadata key : vault.inventory()) {
            System.out.println(
                    key.keyId() + " | " + key.status()
            );
        }

        // Policy evaluation.
        PolicyService policyService = new PolicyService();

        policyService.register(
                new EncryptionPolicy(
                        "REST-001",
                        ProtectionLocation.AT_REST,
                        EncryptionType.SYMMETRIC,
                        256,
                        true,
                        false,
                        true
                )
        );

        policyService.register(
                new EncryptionPolicy(
                        "TRANSIT-001",
                        ProtectionLocation.IN_TRANSIT,
                        EncryptionType.HYBRID,
                        256,
                        true,
                        true,
                        true
                )
        );

        EncryptionRequest valid = new EncryptionRequest(
                "customer-record-001",
                ProtectionLocation.AT_REST,
                EncryptionType.SYMMETRIC,
                "AES-256-GCM",
                second,
                256,
                true,
                true,
                false
        );

        PolicyResult allowed = policyService.evaluate(valid);

        System.out.println(
                "\nValid storage request: " + allowed.decision()
        );

        EncryptionRequest invalid = new EncryptionRequest(
                "customer-record-002",
                ProtectionLocation.AT_REST,
                EncryptionType.SYMMETRIC,
                "AES-128-CBC",
                second,
                128,
                false,
                false,
                false
        );

        PolicyResult denied = policyService.evaluate(invalid);

        System.out.println(
                "Weak encryption request: " + denied.decision()
        );

        denied.reasons().forEach(
                reason -> System.out.println("Rejected: " + reason)
        );

        System.out.println(
                "\nSHA-256 fingerprint: " + fingerprint(plaintext)
        );
    }

    public static void main(String[] args) {
        try {
            demonstrate();
        } catch (Exception exception) {
            System.err.println(
                    "Encryption workflow failed: " +
                    exception.getMessage()
            );

            System.exit(1);
        }
    }
}
