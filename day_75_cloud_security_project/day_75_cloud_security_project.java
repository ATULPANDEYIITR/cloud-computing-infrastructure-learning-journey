import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Collectors;

/**
 * SECURE CLOUD ENVIRONMENT
 *
 * Java 17 enterprise governance implementation.
 *
 * Components:
 * - IAM identity and policy management
 * - Role-based access decisions
 * - Encryption key lifecycle
 * - Storage security
 * - Network segmentation
 * - Audit event management
 * - Security posture assessment
 *
 * Encryption operations are delegated to a conceptual managed KMS.
 * No homemade cryptographic algorithm is implemented.
 */

public class CloudSecurityEnterprise {

    // ========================================================
    // ENUMERATIONS
    // ========================================================

    enum Effect {
        ALLOW,
        DENY
    }

    enum IdentityStatus {
        ACTIVE,
        SUSPENDED,
        DISABLED
    }

    enum KeyStatus {
        ENABLED,
        DISABLED
    }

    enum ResourceStatus {
        ACTIVE,
        ENCRYPTED,
        BLOCKED
    }

    enum Environment {
        DEVELOPMENT,
        STAGING,
        PRODUCTION
    }

    enum Severity {
        LOW,
        MEDIUM,
        HIGH,
        CRITICAL
    }

    // ========================================================
    // EXCEPTIONS
    // ========================================================

    static class SecurityException extends RuntimeException {
        SecurityException(String message) {
            super(message);
        }
    }

    static class AuthorizationException extends SecurityException {
        AuthorizationException(String message) {
            super(message);
        }
    }

    static class ValidationException extends SecurityException {
        ValidationException(String message) {
            super(message);
        }
    }

    // ========================================================
    // VALIDATION UTILITIES
    // ========================================================

    static void requireText(String value, String field) {
        if (
            value == null ||
            value.isBlank() ||
            value.length() > 128
        ) {
            throw new ValidationException(
                "Invalid " + field
            );
        }
    }

    static boolean matches(String pattern, String value) {
        if (pattern.equals("*")) {
            return true;
        }

        if (pattern.endsWith("*")) {
            return value.startsWith(
                pattern.substring(0, pattern.length() - 1)
            );
        }

        return pattern.equals(value);
    }

    // ========================================================
    // IAM POLICY DOMAIN
    // ========================================================

    record PolicyStatement(
        Effect effect,
        Set<String> actions,
        Set<String> resources
    ) {
        PolicyStatement {
            Objects.requireNonNull(effect);

            if (
                actions == null ||
                resources == null ||
                actions.isEmpty() ||
                resources.isEmpty()
            ) {
                throw new ValidationException(
                    "IAM actions and resources are required"
                );
            }

            actions = Set.copyOf(actions);
            resources = Set.copyOf(resources);
        }
    }

    static final class IAMPolicy {

        private final String name;
        private final List<PolicyStatement> statements =
            new ArrayList<>();

        IAMPolicy(
            String name,
            List<PolicyStatement> statements
        ) {
            requireText(name, "policy name");

            this.name = name;

            if (statements != null) {
                this.statements.addAll(statements);
            }
        }

        void addStatement(PolicyStatement statement) {
            statements.add(
                Objects.requireNonNull(statement)
            );
        }

        boolean permits(String action, String resource) {

            boolean allowed = false;

            for (PolicyStatement statement : statements) {

                boolean actionMatch = statement.actions()
                    .stream()
                    .anyMatch(pattern -> matches(pattern, action));

                boolean resourceMatch = statement.resources()
                    .stream()
                    .anyMatch(pattern -> matches(pattern, resource));

                if (!actionMatch || !resourceMatch) {
                    continue;
                }

                if (statement.effect() == Effect.DENY) {
                    return false;
                }

                if (statement.effect() == Effect.ALLOW) {
                    allowed = true;
                }
            }

            return allowed;
        }

        String name() {
            return name;
        }
    }

    // ========================================================
    // IDENTITY MANAGEMENT
    // ========================================================

    static final class Identity {

        private final String id;
        private final IAMPolicy policy;
        private IdentityStatus status;
        private boolean mfaEnabled;
        private final Set<String> permissionsBoundaries;

        Identity(
            String id,
            IAMPolicy policy,
            IdentityStatus status,
            boolean mfaEnabled
        ) {
            requireText(id, "identity ID");

            this.id = id;
            this.policy = Objects.requireNonNull(policy);
            this.status = Objects.requireNonNull(status);
            this.mfaEnabled = mfaEnabled;
            this.permissionsBoundaries = new HashSet<>();
        }

        void suspend() {
            status = IdentityStatus.SUSPENDED;
        }

        void enableMFA() {
            mfaEnabled = true;
        }

        void addBoundary(String resourcePattern) {
            requireText(resourcePattern, "boundary");

            permissionsBoundaries.add(resourcePattern);
        }

        boolean withinBoundary(String resource) {
            return permissionsBoundaries.isEmpty() ||
                permissionsBoundaries.stream()
                    .anyMatch(pattern -> matches(pattern, resource));
        }
    }

    static final class IAMService {

        private final Map<String, Identity> identities =
            new ConcurrentHashMap<>();

        void register(Identity identity) {
            Identity previous = identities.putIfAbsent(
                identity.id,
                identity
            );

            if (previous != null) {
                throw new ValidationException(
                    "Identity already registered"
                );
            }
        }

        boolean authorize(
            String identityId,
            String action,
            String resource,
            boolean requireMFA
        ) {

            Identity identity = identities.get(identityId);

            if (
                identity == null ||
                identity.status != IdentityStatus.ACTIVE
            ) {
                return false;
            }

            if (requireMFA && !identity.mfaEnabled) {
                return false;
            }

            if (!identity.withinBoundary(resource)) {
                return false;
            }

            return identity.policy.permits(action, resource);
        }

        List<Identity> identities() {
            return List.copyOf(identities.values());
        }
    }

    // ========================================================
    // KEY MANAGEMENT
    // ========================================================

    record ManagedKey(
        String alias,
        String keyId,
        String algorithm,
        int version,
        KeyStatus status,
        Instant createdAt
    ) {}

    static final class KeyManagementService {

        private final Map<String, ManagedKey> keys =
            new ConcurrentHashMap<>();

        private final AtomicLong versionCounter =
            new AtomicLong(1000);

        ManagedKey createKey(String alias) {
            requireText(alias, "key alias");

            ManagedKey key = new ManagedKey(
                alias,
                UUID.randomUUID().toString(),
                "AES-256-GCM",
                1,
                KeyStatus.ENABLED,
                Instant.now()
            );

            if (keys.putIfAbsent(alias, key) != null) {
                throw new ValidationException(
                    "Duplicate key alias"
                );
            }

            return key;
        }

        ManagedKey rotate(String alias) {
            ManagedKey current = keys.get(alias);

            if (
                current == null ||
                current.status() != KeyStatus.ENABLED
            ) {
                throw new SecurityException(
                    "Key unavailable for rotation"
                );
            }

            ManagedKey rotated = new ManagedKey(
                alias,
                UUID.randomUUID().toString(),
                current.algorithm(),
                (int) versionCounter.incrementAndGet(),
                KeyStatus.ENABLED,
                Instant.now()
            );

            keys.put(alias, rotated);

            return rotated;
        }

        void disable(String alias) {
            ManagedKey current = keys.get(alias);

            if (current == null) {
                throw new ValidationException("Unknown key");
            }

            keys.put(alias, new ManagedKey(
                current.alias(),
                current.keyId(),
                current.algorithm(),
                current.version(),
                KeyStatus.DISABLED,
                current.createdAt()
            ));
        }

        Optional<ManagedKey> get(String alias) {
            return Optional.ofNullable(keys.get(alias));
        }

        boolean isEnabled(String keyId) {
            return keys.values().stream().anyMatch(key ->
                key.keyId().equals(keyId) &&
                key.status() == KeyStatus.ENABLED
            );
        }
    }

    // ========================================================
    // CLOUD STORAGE
    // ========================================================

    record EncryptionMetadata(
        String keyId,
        String algorithm,
        Instant encryptedAt
    ) {}

    static final class StorageResource {

        private final String id;
        private final String owner;
        private final Environment environment;

        private ResourceStatus status;
        private EncryptionMetadata encryption;

        StorageResource(
            String id,
            String owner,
            Environment environment
        ) {
            requireText(id, "resource ID");
            requireText(owner, "owner");

            this.id = id;
            this.owner = owner;
            this.environment = Objects.requireNonNull(environment);
            this.status = ResourceStatus.ACTIVE;
        }
    }

    static final class StorageService {

        private final Map<String, StorageResource> resources =
            new ConcurrentHashMap<>();

        private final KeyManagementService kms;

        StorageService(KeyManagementService kms) {
            this.kms = kms;
        }

        void provision(StorageResource resource) {
            if (resources.putIfAbsent(
                resource.id,
                resource
            ) != null) {
                throw new ValidationException(
                    "Resource already exists"
                );
            }
        }

        void encrypt(String resourceId, String keyId) {
            StorageResource resource = resources.get(resourceId);

            if (resource == null) {
                throw new ValidationException(
                    "Storage resource not found"
                );
            }

            if (!kms.isEnabled(keyId)) {
                throw new SecurityException(
                    "Encryption key unavailable"
                );
            }

            resource.encryption = new EncryptionMetadata(
                keyId,
                "AES-256-GCM",
                Instant.now()
            );

            resource.status = ResourceStatus.ENCRYPTED;
        }

        boolean isSecure(String resourceId) {
            StorageResource resource = resources.get(resourceId);

            return resource != null &&
                resource.status == ResourceStatus.ENCRYPTED &&
                resource.encryption != null &&
                kms.isEnabled(resource.encryption.keyId());
        }

        List<StorageResource> resources() {
            return List.copyOf(resources.values());
        }
    }

    // ========================================================
    // NETWORK ISOLATION
    // ========================================================

    record NetworkRule(
        String source,
        String destination,
        int port,
        String protocol,
        Effect effect
    ) {
        NetworkRule {
            requireText(source, "source");
            requireText(destination, "destination");

            if (port < 1 || port > 65535) {
                throw new ValidationException(
                    "Invalid network port"
                );
            }

            if (!Set.of("TCP", "UDP", "ICMP").contains(protocol)) {
                throw new ValidationException(
                    "Unsupported network protocol"
                );
            }

            Objects.requireNonNull(effect);
        }
    }

    static final class NetworkSecurityGroup {

        private final String name;
        private final List<NetworkRule> rules =
            new ArrayList<>();

        NetworkSecurityGroup(String name) {
            requireText(name, "network group");
            this.name = name;
        }

        synchronized void addRule(NetworkRule rule) {
            rules.add(rule);
        }

        synchronized boolean permits(
            String source,
            String destination,
            int port,
            String protocol
        ) {

            boolean allowed = false;

            for (NetworkRule rule : rules) {

                if (
                    !matches(rule.source(), source) ||
                    !matches(rule.destination(), destination) ||
                    rule.port() != port ||
                    !rule.protocol().equals(protocol)
                ) {
                    continue;
                }

                if (rule.effect() == Effect.DENY) {
                    return false;
                }

                allowed = true;
            }

            return allowed;
        }

        synchronized int ruleCount() {
            return rules.size();
        }

        String name() {
            return name;
        }
    }

    // ========================================================
    // AUDIT DOMAIN
    // ========================================================

    record AuditEvent(
        long sequence,
        String eventId,
        Instant timestamp,
        String actor,
        String action,
        String resource,
        String outcome,
        Severity severity
    ) {}

    static final class AuditService {

        private final List<AuditEvent> events =
            Collections.synchronizedList(new ArrayList<>());

        private final AtomicLong sequence = new AtomicLong();

        AuditEvent record(
            String actor,
            String action,
            String resource,
            String outcome,
            Severity severity
        ) {

            AuditEvent event = new AuditEvent(
                sequence.incrementAndGet(),
                UUID.randomUUID().toString(),
                Instant.now(),
                actor,
                action,
                resource,
                outcome,
                severity
            );

            events.add(event);

            return event;
        }

        List<AuditEvent> events() {
            synchronized (events) {
                return List.copyOf(events);
            }
        }

        Map<Severity, Long> aggregate() {
            synchronized (events) {
                return events.stream().collect(
                    Collectors.groupingBy(
                        AuditEvent::severity,
                        Collectors.counting()
                    )
                );
            }
        }
    }

    // ========================================================
    // SECURITY POSTURE
    // ========================================================

    record SecurityFinding(
        String category,
        String resource,
        Severity severity,
        String description
    ) {}

    static final class SecurityAssessmentService {

        List<SecurityFinding> evaluate(
            IAMService iam,
            StorageService storage,
            NetworkSecurityGroup network
        ) {

            List<SecurityFinding> findings = new ArrayList<>();

            for (Identity identity : iam.identities()) {
                if (
                    identity.status == IdentityStatus.ACTIVE &&
                    !identity.mfaEnabled
                ) {
                    findings.add(new SecurityFinding(
                        "IAM",
                        identity.id,
                        Severity.HIGH,
                        "Active identity lacks MFA"
                    ));
                }
            }

            for (StorageResource resource : storage.resources()) {
                if (!storage.isSecure(resource.id)) {
                    findings.add(new SecurityFinding(
                        "ENCRYPTION",
                        resource.id,
                        Severity.CRITICAL,
                        "Storage is not protected by an enabled key"
                    ));
                }
            }

            if (network.ruleCount() == 0) {
                findings.add(new SecurityFinding(
                    "NETWORK",
                    network.name(),
                    Severity.HIGH,
                    "Network policy contains no explicit rules"
                ));
            }

            return List.copyOf(findings);
        }
    }

    // ========================================================
    // ENTERPRISE GOVERNANCE SERVICE
    // ========================================================

    static final class CloudSecurityService {

        private final IAMService iam = new IAMService();

        private final KeyManagementService kms =
            new KeyManagementService();

        private final StorageService storage =
            new StorageService(kms);

        private final NetworkSecurityGroup network =
            new NetworkSecurityGroup("production-vpc");

        private final AuditService audit =
            new AuditService();

        private final SecurityAssessmentService assessment =
            new SecurityAssessmentService();

        void registerIdentity(Identity identity) {
            iam.register(identity);
        }

        ManagedKey createKey(String alias) {
            return kms.createKey(alias);
        }

        void provisionStorage(StorageResource resource) {
            storage.provision(resource);
        }

        void encryptStorage(String resource, String keyId) {
            storage.encrypt(resource, keyId);
        }

        void addNetworkRule(NetworkRule rule) {
            network.addRule(rule);
        }

        boolean execute(
            String identity,
            String action,
            String resource
        ) {

            boolean permitted = iam.authorize(
                identity,
                action,
                resource,
                true
            );

            audit.record(
                identity,
                action,
                resource,
                permitted ? "ALLOWED" : "DENIED",
                permitted ? Severity.LOW : Severity.HIGH
            );

            return permitted;
        }

        List<SecurityFinding> assess() {
            return assessment.evaluate(iam, storage, network);
        }

        void printReport() {

            List<SecurityFinding> findings = assess();

            System.out.println("\nCLOUD SECURITY REPORT");

            System.out.println(
                "Identities: " + iam.identities().size()
            );

            System.out.println(
                "Storage resources: " + storage.resources().size()
            );

            System.out.println(
                "Audit events: " + audit.events().size()
            );

            System.out.println(
                "Findings: " + findings.size()
            );

            findings.forEach(finding ->
                System.out.println(
                    "[" + finding.severity() + "] " +
                    finding.category() + " | " +
                    finding.resource() + " | " +
                    finding.description()
                )
            );

            System.out.println(
                "Security status: " +
                (findings.isEmpty() ? "COMPLIANT" : "ACTION REQUIRED")
            );

            System.out.println(
                "Audit aggregation: " + audit.aggregate()
            );
        }
    }

    // ========================================================
    // INTEGRATION TESTS
    // ========================================================

    static void runTests() {

        CloudSecurityService service = new CloudSecurityService();

        IAMPolicy policy = new IAMPolicy(
            "application-reader",
            List.of(
                new PolicyStatement(
                    Effect.ALLOW,
                    Set.of("storage:read"),
                    Set.of("bucket:production/*")
                ),
                new PolicyStatement(
                    Effect.DENY,
                    Set.of("storage:delete"),
                    Set.of("*")
                )
            )
        );

        Identity identity = new Identity(
            "application-service",
            policy,
            IdentityStatus.ACTIVE,
            true
        );

        identity.addBoundary("bucket:production/*");

        service.registerIdentity(identity);

        if (!service.execute(
            "application-service",
            "storage:read",
            "bucket:production/reports"
        )) {
            throw new AssertionError("IAM allow failed");
        }

        if (service.execute(
            "application-service",
            "storage:delete",
            "bucket:production/reports"
        )) {
            throw new AssertionError("Explicit deny failed");
        }

        if (service.execute(
            "application-service",
            "storage:read",
            "bucket:development/reports"
        )) {
            throw new AssertionError("Permissions boundary failed");
        }

        ManagedKey key = service.createKey("production-key");

        service.provisionStorage(new StorageResource(
            "database-backup",
            "database-team",
            Environment.PRODUCTION
        ));

        service.encryptStorage(
            "database-backup",
            key.keyId()
        );

        service.addNetworkRule(new NetworkRule(
            "application-subnet",
            "database-subnet",
            5432,
            "TCP",
            Effect.ALLOW
        ));

        service.addNetworkRule(new NetworkRule(
            "internet",
            "database-subnet",
            5432,
            "TCP",
            Effect.DENY
        ));

        if (!service.network.permits(
            "application-subnet",
            "database-subnet",
            5432,
            "TCP"
        )) {
            throw new AssertionError("Network allow failed");
        }

        if (service.network.permits(
            "internet",
            "database-subnet",
            5432,
            "TCP"
        )) {
            throw new AssertionError("Network deny failed");
        }

        if (!service.assess().isEmpty()) {
            throw new AssertionError(
                "Unexpected security findings"
            );
        }

        System.out.println("All Java 17 security tests passed.");

        service.printReport();
    }

    // ========================================================
    // APPLICATION ENTRY POINT
    // ========================================================

    public static void main(String[] args) {

        try {
            runTests();
        } catch (RuntimeException exception) {
            System.err.println(
                "Cloud security failure: " +
                exception.getMessage()
            );

            System.exit(1);
        }
    }
}
