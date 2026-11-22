import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.regex.Pattern;

/*
 * Enterprise Container Registry Governance System.
 *
 * Java 17
 * No third-party dependencies.
 *
 * Provides explicit domain types, access-control policies, image
 * lifecycle transitions, immutable releases, digest resolution,
 * distribution, audit events, and garbage collection.
 */

public class ContainerRegistryEnterprise {

    enum Role {
        READER,
        WRITER,
        ADMIN
    }

    enum Operation {
        PUSH,
        PULL,
        DELETE
    }

    enum ImageState {
        AVAILABLE,
        QUARANTINED,
        DELETED
    }

    enum RegistryEventType {
        IMAGE_PUSHED,
        IMAGE_PULLED,
        TAG_DELETED,
        IMAGE_QUARANTINED,
        GARBAGE_COLLECTED
    }

    static class RegistryException extends RuntimeException {
        RegistryException(String message) {
            super(message);
        }
    }

    record ImageLayer(String digest, long sizeBytes) {
        ImageLayer {
            if (
                digest == null ||
                !digest.matches("sha256:[a-f0-9]{64}")
            ) {
                throw new IllegalArgumentException(
                    "Invalid layer digest."
                );
            }

            if (sizeBytes <= 0) {
                throw new IllegalArgumentException(
                    "Layer size must be positive."
                );
            }
        }
    }

    record ImageManifest(
        String mediaType,
        String configDigest,
        List<ImageLayer> layers,
        String architecture,
        String operatingSystem
    ) {
        ImageManifest {
            Objects.requireNonNull(mediaType);
            Objects.requireNonNull(configDigest);
            Objects.requireNonNull(layers);
            Objects.requireNonNull(architecture);
            Objects.requireNonNull(operatingSystem);

            if (!configDigest.matches("sha256:[a-f0-9]{64}")) {
                throw new IllegalArgumentException(
                    "Invalid config digest."
                );
            }

            if (layers.isEmpty()) {
                throw new IllegalArgumentException(
                    "Manifest must contain image layers."
                );
            }

            layers = List.copyOf(layers);

            if (!Set.of("amd64", "arm64", "arm", "386")
                    .contains(architecture)) {
                throw new IllegalArgumentException(
                    "Unsupported architecture."
                );
            }
        }

        long totalSize() {
            return layers.stream()
                .mapToLong(ImageLayer::sizeBytes)
                .sum();
        }

        String digest() {
            StringBuilder canonical = new StringBuilder()
                .append(mediaType)
                .append('|')
                .append(configDigest)
                .append('|')
                .append(architecture)
                .append('|')
                .append(operatingSystem);

            layers.stream()
                .map(ImageLayer::digest)
                .sorted()
                .forEach(layer -> canonical.append('|').append(layer));

            return sha256(canonical.toString());
        }
    }

    static class ImageArtifact {
        private final ImageManifest manifest;
        private final String digest;
        private final Instant createdAt;
        private ImageState state;
        private long pullCount;

        ImageArtifact(ImageManifest manifest) {
            this.manifest = manifest;
            this.digest = manifest.digest();
            this.createdAt = Instant.now();
            this.state = ImageState.AVAILABLE;
            this.pullCount = 0;
        }

        ImageManifest manifest() {
            return manifest;
        }

        String digest() {
            return digest;
        }

        ImageState state() {
            return state;
        }

        long pullCount() {
            return pullCount;
        }

        void recordPull() {
            if (state != ImageState.AVAILABLE) {
                throw new RegistryException(
                    "Unavailable image cannot be pulled."
                );
            }

            pullCount++;
        }

        void quarantine() {
            if (state != ImageState.AVAILABLE) {
                throw new RegistryException(
                    "Only available images can be quarantined."
                );
            }

            state = ImageState.QUARANTINED;
        }

        void restore() {
            if (state != ImageState.QUARANTINED) {
                throw new RegistryException(
                    "Image is not quarantined."
                );
            }

            state = ImageState.AVAILABLE;
        }

        void delete() {
            if (state == ImageState.DELETED) {
                throw new RegistryException(
                    "Image is already deleted."
                );
            }

            state = ImageState.DELETED;
        }
    }

    record AuditEvent(
        Instant timestamp,
        String actor,
        RegistryEventType eventType,
        String repository,
        String reference,
        String outcome
    ) {}

    static final class RegistryUser {
        private final String username;
        private final String credentialHash;
        private final Map<String, Role> repositoryRoles =
            new HashMap<>();
        private boolean active = true;

        RegistryUser(String username, String credential) {
            this.username = username;
            this.credentialHash = sha256(credential);
        }

        boolean authenticate(String credential) {
            return active &&
                MessageDigest.isEqual(
                    credentialHash.getBytes(StandardCharsets.UTF_8),
                    sha256(credential).getBytes(StandardCharsets.UTF_8)
                );
        }

        String username() {
            return username;
        }

        void grant(String repository, Role role) {
            repositoryRoles.put(repository, role);
        }

        Role roleFor(String repository) {
            return repositoryRoles.get(repository);
        }

        void deactivate() {
            active = false;
        }
    }

    record RegistryPolicy(
        boolean privateRepository,
        boolean immutableTags,
        boolean requireVerifiedImages,
        Set<String> allowedArchitectures,
        Set<String> protectedTags
    ) {
        RegistryPolicy {
            allowedArchitectures = Set.copyOf(allowedArchitectures);
            protectedTags = Set.copyOf(protectedTags);
        }

        void evaluate(
            RegistryUser user,
            String repository,
            Operation operation,
            ImageManifest manifest
        ) {
            Role role = user.roleFor(repository);

            if (
                privateRepository &&
                role == null
            ) {
                throw new RegistryException(
                    "Private repository access denied."
                );
            }

            boolean allowed = switch (operation) {
                case PULL -> role == Role.READER ||
                             role == Role.WRITER ||
                             role == Role.ADMIN;
                case PUSH -> role == Role.WRITER ||
                             role == Role.ADMIN;
                case DELETE -> role == Role.ADMIN;
            };

            if (!privateRepository && operation == Operation.PULL) {
                allowed = true;
            }

            if (!allowed) {
                throw new RegistryException(
                    "Operation denied by repository policy."
                );
            }

            if (
                operation == Operation.PUSH &&
                !allowedArchitectures.contains(manifest.architecture())
            ) {
                throw new RegistryException(
                    "Image architecture is not permitted."
                );
            }
        }
    }

    static final class Repository {
        private final String name;
        private final RegistryPolicy policy;
        private final Map<String, String> tags = new HashMap<>();
        private final Map<String, ImageArtifact> artifacts =
            new HashMap<>();

        Repository(String name, RegistryPolicy policy) {
            this.name = name;
            this.policy = policy;
        }

        String name() {
            return name;
        }

        RegistryPolicy policy() {
            return policy;
        }

        ImageArtifact resolve(String reference) {
            String digest = reference.startsWith("sha256:")
                ? reference
                : tags.get(reference);

            if (digest == null) {
                throw new RegistryException(
                    "Image reference does not exist."
                );
            }

            ImageArtifact artifact = artifacts.get(digest);

            if (
                artifact == null ||
                artifact.state() != ImageState.AVAILABLE
            ) {
                throw new RegistryException(
                    "Image is unavailable."
                );
            }

            return artifact;
        }
    }

    static final class RegistryService {
        private static final Pattern REPOSITORY_PATTERN =
            Pattern.compile(
                "^[a-z0-9]+(?:[._/-][a-z0-9]+)*$"
            );

        private static final Pattern TAG_PATTERN =
            Pattern.compile(
                "^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$"
            );

        private final String registryName;
        private final Map<String, RegistryUser> users =
            new HashMap<>();
        private final Map<String, Repository> repositories =
            new HashMap<>();
        private final List<AuditEvent> audit =
            new ArrayList<>();

        RegistryService(String registryName) {
            if (registryName == null || registryName.isBlank()) {
                throw new IllegalArgumentException(
                    "Registry name is required."
                );
            }

            this.registryName = registryName;
        }

        void addUser(String username, String credential) {
            if (
                username == null ||
                username.isBlank() ||
                credential == null ||
                credential.length() < 12
            ) {
                throw new IllegalArgumentException(
                    "Invalid user credentials."
                );
            }

            if (users.containsKey(username)) {
                throw new RegistryException(
                    "User already exists."
                );
            }

            users.put(
                username,
                new RegistryUser(username, credential)
            );
        }

        void createRepository(
            String name,
            RegistryPolicy policy
        ) {
            if (!REPOSITORY_PATTERN.matcher(name).matches()) {
                throw new IllegalArgumentException(
                    "Invalid repository name."
                );
            }

            if (repositories.containsKey(name)) {
                throw new RegistryException(
                    "Repository already exists."
                );
            }

            repositories.put(
                name,
                new Repository(name, policy)
            );
        }

        private RegistryUser authenticate(
            String username,
            String credential
        ) {
            RegistryUser user = users.get(username);

            if (
                user == null ||
                credential == null ||
                !user.authenticate(credential)
            ) {
                throw new RegistryException(
                    "Authentication failed."
                );
            }

            return user;
        }

        void grant(
            String adminName,
            String adminCredential,
            String username,
            String repositoryName,
            Role role
        ) {
            RegistryUser admin = authenticate(
                adminName,
                adminCredential
            );

            RegistryUser target = users.get(username);
            Repository repository = repositories.get(repositoryName);

            if (target == null || repository == null) {
                throw new RegistryException(
                    "User or repository not found."
                );
            }

            repository.policy().evaluate(
                admin,
                repositoryName,
                Operation.DELETE,
                new ImageManifest(
                    "application/vnd.oci.image.manifest.v1+json",
                    "sha256:" + "0".repeat(64),
                    List.of(new ImageLayer(
                        "sha256:" + "1".repeat(64),
                        1
                    )),
                    "amd64",
                    "linux"
                )
            );

            target.grant(repositoryName, role);
        }

        private void record(
            String actor,
            RegistryEventType eventType,
            String repository,
            String reference,
            String outcome
        ) {
            audit.add(new AuditEvent(
                Instant.now(),
                actor,
                eventType,
                repository,
                reference,
                outcome
            ));
        }

        String push(
            String username,
            String credential,
            String repositoryName,
            String tag,
            ImageManifest manifest,
            boolean verified
        ) {
            RegistryUser user = authenticate(username, credential);
            Repository repository = repositories.get(repositoryName);

            if (repository == null) {
                throw new RegistryException(
                    "Repository not found."
                );
            }

            if (!TAG_PATTERN.matcher(tag).matches()) {
                throw new IllegalArgumentException(
                    "Invalid image tag."
                );
            }

            repository.policy().evaluate(
                user,
                repositoryName,
                Operation.PUSH,
                manifest
            );

            if (
                repository.policy().requireVerifiedImages() &&
                !verified
            ) {
                throw new RegistryException(
                    "Image verification required."
                );
            }

            String digest = manifest.digest();
            String currentDigest = repository.tags.get(tag);

            if (
                currentDigest != null &&
                !currentDigest.equals(digest) &&
                (
                    repository.policy().immutableTags() ||
                    repository.policy().protectedTags().contains(tag)
                )
            ) {
                throw new RegistryException(
                    "Tag reassignment is prohibited."
                );
            }

            repository.artifacts.putIfAbsent(
                digest,
                new ImageArtifact(manifest)
            );

            repository.tags.put(tag, digest);

            record(
                username,
                RegistryEventType.IMAGE_PUSHED,
                repositoryName,
                tag,
                "SUCCESS"
            );

            return digest;
        }

        ImageArtifact pull(
            String username,
            String credential,
            String repositoryName,
            String reference
        ) {
            RegistryUser user = authenticate(username, credential);
            Repository repository = repositories.get(repositoryName);

            if (repository == null) {
                throw new RegistryException(
                    "Repository not found."
                );
            }

            repository.policy().evaluate(
                user,
                repositoryName,
                Operation.PULL,
                new ImageManifest(
                    "application/vnd.oci.image.manifest.v1+json",
                    "sha256:" + "0".repeat(64),
                    List.of(new ImageLayer(
                        "sha256:" + "1".repeat(64),
                        1
                    )),
                    "amd64",
                    "linux"
                )
            );

            ImageArtifact artifact = repository.resolve(reference);
            artifact.recordPull();

            record(
                username,
                RegistryEventType.IMAGE_PULLED,
                repositoryName,
                reference,
                "SUCCESS"
            );

            return artifact;
        }

        void quarantine(
            String adminName,
            String adminCredential,
            String repositoryName,
            String digest
        ) {
            RegistryUser admin = authenticate(
                adminName,
                adminCredential
            );

            Repository repository = repositories.get(repositoryName);

            if (repository == null) {
                throw new RegistryException(
                    "Repository not found."
                );
            }

            ImageManifest sample = new ImageManifest(
                "application/vnd.oci.image.manifest.v1+json",
                "sha256:" + "0".repeat(64),
                List.of(new ImageLayer(
                    "sha256:" + "1".repeat(64),
                    1
                )),
                "amd64",
                "linux"
            );

            repository.policy().evaluate(
                admin,
                repositoryName,
                Operation.DELETE,
                sample
            );

            ImageArtifact artifact = repository.artifacts.get(digest);

            if (artifact == null) {
                throw new RegistryException(
                    "Artifact not found."
                );
            }

            artifact.quarantine();

            record(
                adminName,
                RegistryEventType.IMAGE_QUARANTINED,
                repositoryName,
                digest,
                "SUCCESS"
            );
        }

        void deleteTag(
            String adminName,
            String adminCredential,
            String repositoryName,
            String tag
        ) {
            RegistryUser admin = authenticate(
                adminName,
                adminCredential
            );

            Repository repository = repositories.get(repositoryName);

            if (repository == null) {
                throw new RegistryException(
                    "Repository not found."
                );
            }

            repository.policy().evaluate(
                admin,
                repositoryName,
                Operation.DELETE,
                new ImageManifest(
                    "application/vnd.oci.image.manifest.v1+json",
                    "sha256:" + "0".repeat(64),
                    List.of(new ImageLayer(
                        "sha256:" + "1".repeat(64),
                        1
                    )),
                    "amd64",
                    "linux"
                )
            );

            if (repository.policy().protectedTags().contains(tag)) {
                throw new RegistryException(
                    "Protected tag cannot be deleted."
                );
            }

            if (repository.tags.remove(tag) == null) {
                throw new RegistryException(
                    "Tag does not exist."
                );
            }

            record(
                adminName,
                RegistryEventType.TAG_DELETED,
                repositoryName,
                tag,
                "SUCCESS"
            );
        }

        int garbageCollect(
            String adminName,
            String adminCredential,
            String repositoryName
        ) {
            RegistryUser admin = authenticate(
                adminName,
                adminCredential
            );

            Repository repository = repositories.get(repositoryName);

            if (repository == null) {
                throw new RegistryException(
                    "Repository not found."
                );
            }

            ImageManifest sample = new ImageManifest(
                "application/vnd.oci.image.manifest.v1+json",
                "sha256:" + "0".repeat(64),
                List.of(new ImageLayer(
                    "sha256:" + "1".repeat(64),
                    1
                )),
                "amd64",
                "linux"
            );

            repository.policy().evaluate(
                admin,
                repositoryName,
                Operation.DELETE,
                sample
            );

            Set<String> referenced = new HashSet<>(
                repository.tags.values()
            );

            int before = repository.artifacts.size();

            repository.artifacts.keySet().removeIf(
                digest -> !referenced.contains(digest)
            );

            int removed = before - repository.artifacts.size();

            record(
                adminName,
                RegistryEventType.GARBAGE_COLLECTED,
                repositoryName,
                Integer.toString(removed),
                "SUCCESS"
            );

            return removed;
        }

        void report(String repositoryName) {
            Repository repository = repositories.get(repositoryName);

            if (repository == null) {
                throw new RegistryException(
                    "Repository not found."
                );
            }

            long totalPulls = repository.artifacts.values()
                .stream()
                .mapToLong(ImageArtifact::pullCount)
                .sum();

            System.out.println("\nRegistry: " + registryName);
            System.out.println("Repository: " + repositoryName);
            System.out.println("Tags: " + repository.tags.size());
            System.out.println("Artifacts: " + repository.artifacts.size());
            System.out.println("Pulls: " + totalPulls);

            new TreeMap<>(repository.tags).forEach(
                (tag, digest) ->
                    System.out.println(tag + " -> " + digest)
            );
        }

        void printAudit() {
            audit.forEach(System.out::println);
        }
    }

    private static String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");

            byte[] bytes = digest.digest(
                value.getBytes(StandardCharsets.UTF_8)
            );

            StringBuilder output = new StringBuilder("sha256:");

            for (byte item : bytes) {
                output.append(String.format("%02x", item));
            }

            return output.toString();

        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(
                "SHA-256 is unavailable.",
                exception
            );
        }
    }

    public static void main(String[] args) {
        try {
            RegistryService registry =
                new RegistryService("corporate-registry");

            registry.addUser("admin", "admin-credential-2026");
            registry.addUser("builder", "builder-credential-2026");
            registry.addUser("runtime", "runtime-credential-2026");

            RegistryPolicy policy = new RegistryPolicy(
                true,
                false,
                true,
                Set.of("amd64", "arm64"),
                Set.of("production")
            );

            registry.createRepository(
                "finance/payment-api",
                policy
            );

            // Initial administrator assignment is performed during
            // controlled registry provisioning.
            registry.users.get("admin").grant(
                "finance/payment-api",
                Role.ADMIN
            );

            registry.grant(
                "admin",
                "admin-credential-2026",
                "builder",
                "finance/payment-api",
                Role.WRITER
            );

            registry.grant(
                "admin",
                "admin-credential-2026",
                "runtime",
                "finance/payment-api",
                Role.READER
            );

            ImageManifest version1 = new ImageManifest(
                "application/vnd.oci.image.manifest.v1+json",
                sha256("payment-config-v1"),
                List.of(
                    new ImageLayer(sha256("layer-1"), 1024),
                    new ImageLayer(sha256("layer-2"), 2048)
                ),
                "amd64",
                "linux"
            );

            String digest = registry.push(
                "builder",
                "builder-credential-2026",
                "finance/payment-api",
                "1.0.0",
                version1,
                true
            );

            registry.push(
                "builder",
                "builder-credential-2026",
                "finance/payment-api",
                "production",
                version1,
                true
            );

            ImageArtifact deployment = registry.pull(
                "runtime",
                "runtime-credential-2026",
                "finance/payment-api",
                "production"
            );

            System.out.println(
                "Deployment digest: " + deployment.digest()
            );

            System.out.println(
                "Digest stable: " + digest.equals(deployment.digest())
            );

            ImageManifest version2 = new ImageManifest(
                "application/vnd.oci.image.manifest.v1+json",
                sha256("payment-config-v2"),
                List.of(
                    new ImageLayer(sha256("layer-3"), 4096)
                ),
                "arm64",
                "linux"
            );

            registry.push(
                "builder",
                "builder-credential-2026",
                "finance/payment-api",
                "2.0.0",
                version2,
                true
            );

            try {
                registry.push(
                    "builder",
                    "builder-credential-2026",
                    "finance/payment-api",
                    "production",
                    version2,
                    true
                );
            } catch (RegistryException exception) {
                System.out.println(
                    "Expected protected-tag rejection: " +
                    exception.getMessage()
                );
            }

            try {
                registry.push(
                    "runtime",
                    "runtime-credential-2026",
                    "finance/payment-api",
                    "unauthorized",
                    version2,
                    true
                );
            } catch (RegistryException exception) {
                System.out.println(
                    "Expected writer-permission rejection: " +
                    exception.getMessage()
                );
            }

            registry.report("finance/payment-api");

            System.out.println(
                "Garbage-collected artifacts: " +
                registry.garbageCollect(
                    "admin",
                    "admin-credential-2026",
                    "finance/payment-api"
                )
            );

            registry.printAudit();

        } catch (Exception exception) {
            System.err.println(
                "Registry operation failed: " + exception.getMessage()
            );
            System.exit(1);
        }
    }
}
