import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/*
 * Enterprise object storage governance model.
 *
 * Compile and run:
 *   javac ObjectStorageGovernance.java
 *   java ObjectStorageGovernance
 *
 * Uses Java 17 and only the standard library.
 */
public class ObjectStorageGovernance {

    enum VersioningState {
        ENABLED, SUSPENDED, DISABLED
    }

    enum StorageClass {
        STANDARD, INFREQUENT_ACCESS, ARCHIVE
    }

    enum Action {
        LIST_OBJECTS,
        GET_OBJECT,
        GET_VERSION,
        PUT_OBJECT,
        DELETE_OBJECT,
        DELETE_VERSION,
        RESTORE_OBJECT,
        MANAGE_LIFECYCLE,
        MANAGE_POLICY
    }

    enum Effect {
        ALLOW, DENY
    }

    enum ReviewState {
        CURRENT, NONCURRENT, DELETE_MARKER
    }

    static class StorageException extends RuntimeException {
        StorageException(String message) {
            super(message);
        }
    }

    static final class AccessDeniedException extends StorageException {
        AccessDeniedException(String message) {
            super(message);
        }
    }

    static final class ObjectNotFoundException extends StorageException {
        ObjectNotFoundException(String message) {
            super(message);
        }
    }

    static final class PreconditionFailedException extends StorageException {
        PreconditionFailedException(String message) {
            super(message);
        }
    }

    record Principal(String name, Set<String> roles, boolean authenticated) {
        Principal {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Principal name is required.");
            }
            roles = Set.copyOf(roles);
        }
    }

    record ObjectMetadata(
        String contentType,
        long contentLength,
        String sha256,
        Map<String, String> userMetadata,
        Instant lastModified
    ) {
        ObjectMetadata {
            if (contentType == null || contentType.isBlank()) {
                throw new IllegalArgumentException("Content type is required.");
            }
            if (contentLength < 0) {
                throw new IllegalArgumentException("Content length cannot be negative.");
            }
            if (sha256 == null || !sha256.matches("[0-9a-f]{64}")) {
                throw new IllegalArgumentException("A SHA-256 digest is required.");
            }
            userMetadata = Map.copyOf(userMetadata);
            Objects.requireNonNull(lastModified, "lastModified");
        }
    }

    record PolicyStatement(
        Effect effect,
        Set<Action> actions,
        Set<String> resources,
        Set<String> principals,
        Map<String, String> conditions
    ) {
        PolicyStatement {
            Objects.requireNonNull(effect);
            actions = Set.copyOf(actions);
            resources = Set.copyOf(resources);
            principals = Set.copyOf(principals);
            conditions = Map.copyOf(conditions);

            if (actions.isEmpty() || resources.isEmpty() || principals.isEmpty()) {
                throw new IllegalArgumentException("Policy statement cannot have empty match sets.");
            }
        }
    }

    record LifecycleRule(
        String id,
        String prefix,
        Integer transitionAfterDays,
        StorageClass transitionTarget,
        Integer expireAfterDays,
        Integer noncurrentExpireAfterDays,
        boolean enabled
    ) {
        LifecycleRule {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Lifecycle rule ID is required.");
            }
            if (prefix == null) prefix = "";
            if (transitionAfterDays == null && expireAfterDays == null
                    && noncurrentExpireAfterDays == null) {
                throw new IllegalArgumentException("Lifecycle rule must contain an action.");
            }
            for (Integer days : List.of(
                    transitionAfterDays == null ? 0 : transitionAfterDays,
                    expireAfterDays == null ? 0 : expireAfterDays,
                    noncurrentExpireAfterDays == null ? 0 : noncurrentExpireAfterDays)) {
                if (days < 0) throw new IllegalArgumentException("Lifecycle age cannot be negative.");
            }
        }
    }

    static final class ObjectVersion {
        private final String key;
        private final String versionId;
        private final byte[] payload;
        private final ObjectMetadata metadata;
        private final Instant createdAt;
        private Instant noncurrentSince;
        private Instant retentionUntil;
        private StorageClass storageClass;
        private final boolean deleteMarker;

        ObjectVersion(
            String key,
            String versionId,
            byte[] payload,
            ObjectMetadata metadata,
            Instant createdAt,
            StorageClass storageClass,
            boolean deleteMarker
        ) {
            this.key = key;
            this.versionId = versionId;
            this.payload = payload.clone();
            this.metadata = metadata;
            this.createdAt = createdAt;
            this.storageClass = storageClass;
            this.deleteMarker = deleteMarker;
        }

        String key() { return key; }
        String versionId() { return versionId; }
        byte[] payload() { return payload.clone(); }
        ObjectMetadata metadata() { return metadata; }
        Instant createdAt() { return createdAt; }
        Instant noncurrentSince() { return noncurrentSince; }
        StorageClass storageClass() { return storageClass; }
        boolean deleteMarker() { return deleteMarker; }

        void markNoncurrent(Instant instant) {
            if (!deleteMarker && noncurrentSince == null) noncurrentSince = instant;
        }

        void setStorageClass(StorageClass value) {
            storageClass = value;
        }

        void setRetentionUntil(Instant value) {
            retentionUntil = value;
        }

        boolean retainedAt(Instant now) {
            return retentionUntil != null && now.isBefore(retentionUntil);
        }
    }

    static final class Bucket {
        private static final Pattern NAME_PATTERN =
            Pattern.compile("[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]");

        private final String name;
        private final Principal owner;
        private VersioningState versioningState;
        private final Map<String, List<ObjectVersion>> objects = new HashMap<>();
        private final List<PolicyStatement> policy = new ArrayList<>();
        private final List<LifecycleRule> lifecycleRules = new ArrayList<>();

        Bucket(String name, Principal owner, VersioningState versioningState) {
            if (!NAME_PATTERN.matcher(name).matches()
                    || name.contains("..")
                    || name.contains(".-")
                    || name.contains("-.")) {
                throw new IllegalArgumentException("Invalid bucket name.");
            }
            this.name = name;
            this.owner = Objects.requireNonNull(owner);
            this.versioningState = Objects.requireNonNull(versioningState);
        }

        String name() { return name; }
        Principal owner() { return owner; }
        VersioningState versioningState() { return versioningState; }

        void setVersioningState(VersioningState state) {
            versioningState = Objects.requireNonNull(state);
        }

        void replacePolicy(List<PolicyStatement> statements) {
            policy.clear();
            policy.addAll(statements);
        }

        void replaceLifecycleRules(List<LifecycleRule> rules) {
            Set<String> ids = new HashSet<>();
            for (LifecycleRule rule : rules) {
                if (!ids.add(rule.id())) {
                    throw new IllegalArgumentException("Lifecycle rule IDs must be unique.");
                }
            }
            lifecycleRules.clear();
            lifecycleRules.addAll(rules);
        }

        List<ObjectVersion> versions(String key) {
            return objects.computeIfAbsent(key, ignored -> new ArrayList<>());
        }

        ObjectVersion current(String key) {
            List<ObjectVersion> history = objects.get(key);
            if (history == null || history.isEmpty() || history.get(0).deleteMarker()) {
                return null;
            }
            return history.get(0);
        }

        Map<String, List<ObjectVersion>> objectHistory() {
            return objects;
        }

        List<PolicyStatement> policy() {
            return policy;
        }

        List<LifecycleRule> lifecycleRules() {
            return lifecycleRules;
        }
    }

    static final class StorageService {
        private final Map<String, Bucket> buckets = new HashMap<>();
        private long sequence;

        Bucket createBucket(String name, Principal owner, VersioningState state) {
            if (buckets.containsKey(name)) {
                throw new IllegalArgumentException("Bucket already exists.");
            }
            Bucket bucket = new Bucket(name, owner, state);
            buckets.put(name, bucket);
            return bucket;
        }

        Bucket getBucket(String name) {
            Bucket bucket = buckets.get(name);
            if (bucket == null) throw new StorageException("Bucket not found: " + name);
            return bucket;
        }

        void configurePolicy(Principal actor, String bucketName, List<PolicyStatement> statements) {
            Bucket bucket = getBucket(bucketName);
            if (!actor.name().equals(bucket.owner().name())
                    && !authorize(actor, bucket, Action.MANAGE_POLICY, null, Map.of())) {
                throw new AccessDeniedException("Principal cannot manage bucket policy.");
            }
            bucket.replacePolicy(statements);
        }

        boolean authorize(
            Principal principal,
            Bucket bucket,
            Action action,
            String key,
            Map<String, String> context
        ) {
            if (!principal.authenticated()) return false;
            if (principal.name().equals(bucket.owner().name())) return true;

            String resource = key == null
                ? "arn:object:" + bucket.name()
                : "arn:object:" + bucket.name() + "/" + key;

            List<PolicyStatement> matches = bucket.policy().stream()
                .filter(statement ->
                    statement.principals().contains("*")
                    || statement.principals().contains(principal.name())
                    || statement.principals().stream().anyMatch(principal.roles()::contains))
                .filter(statement -> statement.actions().contains(action))
                .filter(statement -> statement.resources().stream().anyMatch(pattern ->
                    pattern.equals("*")
                    || (pattern.endsWith("*")
                        ? resource.startsWith(pattern.substring(0, pattern.length() - 1))
                        : resource.equals(pattern))))
                .filter(statement -> statement.conditions().entrySet().stream().allMatch(entry ->
                    Objects.equals(context.get(entry.getKey()), entry.getValue())))
                .toList();

            if (matches.stream().anyMatch(s -> s.effect() == Effect.DENY)) return false;
            return matches.stream().anyMatch(s -> s.effect() == Effect.ALLOW);
        }

        void require(
            Principal principal,
            Bucket bucket,
            Action action,
            String key,
            Map<String, String> context
        ) {
            if (!authorize(principal, bucket, action, key, context)) {
                throw new AccessDeniedException(
                    principal.name() + " cannot execute " + action + " on " + key
                );
            }
        }

        ObjectVersion put(
            Principal principal,
            String bucketName,
            String key,
            byte[] payload,
            String contentType,
            Map<String, String> userMetadata,
            String expectedCurrentSha256,
            Map<String, String> context
        ) {
            Bucket bucket = getBucket(bucketName);
            validateKey(key);
            require(principal, bucket, Action.PUT_OBJECT, key, context);

            ObjectVersion current = bucket.current(key);
            if (expectedCurrentSha256 != null
                    && (current == null
                    || !current.metadata().sha256().equals(expectedCurrentSha256))) {
                throw new PreconditionFailedException("Current object checksum changed.");
            }

            Instant now = Instant.now();
            List<ObjectVersion> history = bucket.versions(key);
            if (bucket.versioningState() == VersioningState.DISABLED) {
                history.clear();
            } else {
                history.forEach(version -> version.markNoncurrent(now));
            }

            String versionId = bucket.versioningState() == VersioningState.ENABLED
                ? UUID.randomUUID().toString()
                : "null";

            ObjectMetadata metadata = new ObjectMetadata(
                contentType,
                payload.length,
                digest(payload),
                userMetadata,
                now
            );

            if (bucket.versioningState() == VersioningState.SUSPENDED) {
                history.removeIf(version -> version.versionId().equals("null"));
            }

            ObjectVersion version = new ObjectVersion(
                key, versionId, payload, metadata, now, StorageClass.STANDARD, false
            );
            history.add(0, version);
            return version;
        }

        byte[] get(
            Principal principal,
            String bucketName,
            String key,
            String versionId,
            Map<String, String> context
        ) {
            Bucket bucket = getBucket(bucketName);
            validateKey(key);

            require(
                principal,
                bucket,
                versionId == null ? Action.GET_OBJECT : Action.GET_VERSION,
                key,
                context
            );

            List<ObjectVersion> history = bucket.objectHistory().getOrDefault(key, List.of());
            ObjectVersion selected = versionId == null
                ? bucket.current(key)
                : history.stream()
                    .filter(version -> version.versionId().equals(versionId))
                    .findFirst()
                    .orElse(null);

            if (selected == null || selected.deleteMarker()) {
                throw new ObjectNotFoundException("Object version not found.");
            }
            if (selected.storageClass() == StorageClass.ARCHIVE) {
                throw new StorageException("Archived object must be restored.");
            }
            if (!digest(selected.payload()).equals(selected.metadata().sha256())) {
                throw new StorageException("Object checksum verification failed.");
            }
            return selected.payload();
        }

        void delete(
            Principal principal,
            String bucketName,
            String key,
            String versionId,
            Map<String, String> context
        ) {
            Bucket bucket = getBucket(bucketName);
            validateKey(key);

            require(
                principal,
                bucket,
                versionId == null ? Action.DELETE_OBJECT : Action.DELETE_VERSION,
                key,
                context
            );

            List<ObjectVersion> history = bucket.objectHistory().getOrDefault(key, new ArrayList<>());
            Instant now = Instant.now();

            if (versionId != null) {
                ObjectVersion target = history.stream()
                    .filter(version -> version.versionId().equals(versionId))
                    .findFirst()
                    .orElseThrow(() -> new ObjectNotFoundException("Version not found."));

                if (target.retainedAt(now)) {
                    throw new StorageException("Retention period prevents version deletion.");
                }
                history.remove(target);
            } else if (bucket.versioningState() == VersioningState.ENABLED) {
                history.forEach(version -> version.markNoncurrent(now));
                ObjectMetadata markerMetadata = new ObjectMetadata(
                    "application/x-delete-marker", 0, digest(new byte[0]), Map.of(), now
                );
                history.add(0, new ObjectVersion(
                    key, UUID.randomUUID().toString(), new byte[0],
                    markerMetadata, now, StorageClass.STANDARD, true
                ));
            } else {
                ObjectVersion current = bucket.current(key);
                if (current == null) throw new ObjectNotFoundException("Object not found.");
                if (current.retainedAt(now)) {
                    throw new StorageException("Retention period prevents deletion.");
                }
                history.clear();
                bucket.objectHistory().remove(key);
            }
        }

        Map<String, Integer> executeLifecycle(String bucketName, Instant now) {
            Bucket bucket = getBucket(bucketName);
            Map<String, Integer> counts = new HashMap<>();
            counts.put("transitioned", 0);
            counts.put("expired", 0);
            counts.put("noncurrentDeleted", 0);

            for (String key : new ArrayList<>(bucket.objectHistory().keySet())) {
                List<ObjectVersion> history = bucket.objectHistory().get(key);
                List<LifecycleRule> matchingRules = bucket.lifecycleRules().stream()
                    .filter(LifecycleRule::enabled)
                    .filter(rule -> key.startsWith(rule.prefix()))
                    .toList();

                for (ObjectVersion version : new ArrayList<>(history)) {
                    if (version.deleteMarker()) continue;

                    long ageDays = Duration.between(version.createdAt(), now).toDays();
                    Long noncurrentDays = version.noncurrentSince() == null
                        ? null
                        : Duration.between(version.noncurrentSince(), now).toDays();

                    for (LifecycleRule rule : matchingRules) {
                        if (rule.transitionAfterDays() != null
                                && ageDays >= rule.transitionAfterDays()
                                && version.storageClass() == StorageClass.STANDARD) {
                            version.setStorageClass(rule.transitionTarget());
                            counts.merge("transitioned", 1, Integer::sum);
                        }

                        if (rule.noncurrentExpireAfterDays() != null
                                && noncurrentDays != null
                                && noncurrentDays >= rule.noncurrentExpireAfterDays()
                                && !version.retainedAt(now)) {
                            history.remove(version);
                            counts.merge("noncurrentDeleted", 1, Integer::sum);
                            break;
                        }

                        boolean current = !history.isEmpty()
                            && history.get(0) == version
                            && version.noncurrentSince() == null;

                        if (current && rule.expireAfterDays() != null
                                && ageDays >= rule.expireAfterDays()
                                && !version.retainedAt(now)) {
                            if (bucket.versioningState() == VersioningState.ENABLED) {
                                version.markNoncurrent(now);
                                ObjectMetadata markerMetadata = new ObjectMetadata(
                                    "application/x-delete-marker", 0,
                                    digest(new byte[0]), Map.of(), now
                                );
                                history.add(0, new ObjectVersion(
                                    key, UUID.randomUUID().toString(), new byte[0],
                                    markerMetadata, now, StorageClass.STANDARD, true
                                ));
                            } else {
                                history.remove(version);
                            }
                            counts.merge("expired", 1, Integer::sum);
                            break;
                        }
                    }
                }

                if (history.isEmpty()) bucket.objectHistory().remove(key);
            }
            return Map.copyOf(counts);
        }

        private static void validateKey(String key) {
            if (key == null || key.isBlank() || key.startsWith("/")
                    || key.indexOf('\0') >= 0 || key.getBytes(StandardCharsets.UTF_8).length > 1024) {
                throw new IllegalArgumentException("Invalid object key.");
            }
            for (String segment : key.split("/", -1)) {
                if (segment.equals("..")) {
                    throw new IllegalArgumentException("Parent-directory segments are prohibited.");
                }
            }
        }

        private static String digest(byte[] payload) {
            try {
                return java.util.HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(payload)
                );
            } catch (NoSuchAlgorithmException exception) {
                throw new IllegalStateException("SHA-256 is unavailable.", exception);
            }
        }
    }

    private static PolicyStatement statement(
        Effect effect,
        Set<Action> actions,
        String resource,
        String principal,
        Map<String, String> conditions
    ) {
        return new PolicyStatement(
            effect, actions, Set.of(resource), Set.of(principal), conditions
        );
    }

    public static void main(String[] args) {
        Principal owner = new Principal("platform-owner", Set.of("storage-admin"), true);
        Principal writer = new Principal("report-service", Set.of("report-writer"), true);
        Principal auditor = new Principal("compliance-auditor", Set.of("audit"), true);
        Principal anonymous = new Principal("anonymous", Set.of(), false);

        StorageService service = new StorageService();
        Bucket bucket = service.createBucket(
            "enterprise-records-prod", owner, VersioningState.ENABLED
        );

        service.configurePolicy(owner, bucket.name(), List.of(
            statement(
                Effect.ALLOW,
                EnumSet.of(Action.GET_OBJECT, Action.GET_VERSION),
                "arn:object:enterprise-records-prod/reports/*",
                "audit",
                Map.of()
            ),
            statement(
                Effect.ALLOW,
                EnumSet.of(Action.PUT_OBJECT, Action.GET_OBJECT, Action.DELETE_OBJECT),
                "arn:object:enterprise-records-prod/reports/*",
                "report-writer",
                Map.of("transport", "tls")
            ),
            statement(
                Effect.DENY,
                EnumSet.of(Action.DELETE_OBJECT, Action.DELETE_VERSION),
                "arn:object:enterprise-records-prod/legal/*",
                "*",
                Map.of()
            )
        ));

        service.getBucket(bucket.name()).replaceLifecycleRules(List.of(
            new LifecycleRule(
                "archive-reports",
                "reports/archive/",
                30,
                StorageClass.ARCHIVE,
                null,
                180,
                true
            ),
            new LifecycleRule(
                "temporary-expiration",
                "tmp/",
                null,
                StorageClass.INFREQUENT_ACCESS,
                7,
                null,
                true
            )
        ));

        Map<String, String> tls = Map.of("transport", "tls");

        ObjectVersion first = service.put(
            writer,
            bucket.name(),
            "reports/monthly.json",
            "{\"month\":\"2026-09\",\"incidents\":18}".getBytes(StandardCharsets.UTF_8),
            "application/json",
            Map.of("department", "operations", "classification", "internal"),
            null,
            tls
        );

        ObjectVersion revised = service.put(
            writer,
            bucket.name(),
            "reports/monthly.json",
            "{\"month\":\"2026-09\",\"incidents\":16}".getBytes(StandardCharsets.UTF_8),
            "application/json",
            Map.of("department", "operations", "revision", "verified"),
            first.metadata().sha256(),
            tls
        );

        System.out.println("Current object versions are distinct:");
        System.out.println("Original version: " + first.versionId());
        System.out.println("Revised version:  " + revised.versionId());

        byte[] historic = service.get(
            auditor, bucket.name(), "reports/monthly.json", first.versionId(), Map.of()
        );
        System.out.println("Historical payload: " + new String(historic, StandardCharsets.UTF_8));

        try {
            service.put(
                writer,
                bucket.name(),
                "reports/monthly.json",
                "stale update".getBytes(StandardCharsets.UTF_8),
                "text/plain",
                Map.of(),
                "0".repeat(64),
                tls
            );
        } catch (PreconditionFailedException exception) {
            System.out.println("Conditional write rejected: " + exception.getMessage());
        }

        try {
            service.get(anonymous, bucket.name(), "reports/monthly.json", null, Map.of());
        } catch (AccessDeniedException exception) {
            System.out.println("Unauthenticated access rejected: " + exception.getMessage());
        }

        try {
            service.delete(
                writer, bucket.name(), "legal/retention-register.csv", null, tls
            );
        } catch (AccessDeniedException exception) {
            System.out.println("Protected deletion rejected: " + exception.getMessage());
        }

        service.delete(writer, bucket.name(), "reports/monthly.json", null, tls);
        try {
            service.get(writer, bucket.name(), "reports/monthly.json", null, tls);
        } catch (ObjectNotFoundException exception) {
            System.out.println("Delete marker hides the current key.");
        }

        byte[] retainedVersion = service.get(
            auditor, bucket.name(), "reports/monthly.json", revised.versionId(), Map.of()
        );
        System.out.println("Prior version remains available: "
            + new String(retainedVersion, StandardCharsets.UTF_8));

        System.out.println("Lifecycle rules configured: "
            + bucket.lifecycleRules().stream().map(LifecycleRule::id).collect(Collectors.toList()));
        System.out.println("Review-state vocabulary: " + ReviewState.CURRENT
            + ", " + ReviewState.NONCURRENT + ", " + ReviewState.DELETE_MARKER);
    }
}
