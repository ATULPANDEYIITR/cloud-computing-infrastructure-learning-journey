import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * Deployments and ReplicaSets
 *
 * Enterprise deployment lifecycle, reconciliation, policy validation,
 * rolling updates, and revision-based rollbacks.
 *
 * Java 17. No third-party dependencies.
 */
public class DeploymentManager {

    enum DeploymentPhase {
        PROGRESSING,
        AVAILABLE,
        DEGRADED,
        PAUSED
    }

    enum PodPhase {
        PENDING,
        RUNNING,
        READY,
        FAILED,
        TERMINATING
    }

    static class DeploymentException extends RuntimeException {
        DeploymentException(String message) {
            super(message);
        }
    }

    static class ValidationException extends DeploymentException {
        ValidationException(String message) {
            super(message);
        }
    }

    record ContainerSpec(
        String name,
        String image,
        int port,
        String cpuRequest,
        String memoryRequest
    ) {
        ContainerSpec {
            Objects.requireNonNull(name);
            Objects.requireNonNull(image);
            Objects.requireNonNull(cpuRequest);
            Objects.requireNonNull(memoryRequest);

            if (!name.matches("[a-z][a-z0-9-]{0,62}")) {
                throw new ValidationException("Invalid container name");
            }

            if (!image.matches("[A-Za-z0-9][A-Za-z0-9._/:@-]{0,254}")) {
                throw new ValidationException("Invalid image reference");
            }

            if (port < 1 || port > 65535) {
                throw new ValidationException("Invalid container port");
            }
        }
    }

    record DeploymentSpec(
        String name,
        String namespace,
        int replicas,
        ContainerSpec container,
        int maxSurge,
        int maxUnavailable,
        int revisionHistoryLimit
    ) {
        DeploymentSpec {
            Objects.requireNonNull(name);
            Objects.requireNonNull(namespace);
            Objects.requireNonNull(container);

            if (!name.matches("[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")) {
                throw new ValidationException("Invalid deployment name");
            }

            if (!namespace.matches("[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")) {
                throw new ValidationException("Invalid namespace");
            }

            if (replicas < 0 || replicas > 10000) {
                throw new ValidationException("Invalid replica count");
            }

            if (maxSurge < 0 || maxSurge > 1000) {
                throw new ValidationException("Invalid maxSurge");
            }

            if (maxUnavailable < 0 || maxUnavailable > replicas) {
                throw new ValidationException("Invalid maxUnavailable");
            }

            if (revisionHistoryLimit < 1 || revisionHistoryLimit > 100) {
                throw new ValidationException("Invalid history limit");
            }
        }

        DeploymentSpec withImage(String image) {
            return new DeploymentSpec(
                name,
                namespace,
                replicas,
                new ContainerSpec(
                    container.name(),
                    image,
                    container.port(),
                    container.cpuRequest(),
                    container.memoryRequest()
                ),
                maxSurge,
                maxUnavailable,
                revisionHistoryLimit
            );
        }

        DeploymentSpec withReplicas(int count) {
            return new DeploymentSpec(
                name,
                namespace,
                count,
                container,
                maxSurge,
                maxUnavailable,
                revisionHistoryLimit
            );
        }
    }

    record RevisionRecord(
        int revision,
        String image,
        Instant createdAt
    ) {}

    record AuditEvent(
        String deployment,
        String event,
        String details,
        Instant timestamp
    ) {}

    static class Pod {
        private final String id = UUID.randomUUID().toString();
        private final String image;
        private final String replicaSetId;
        private PodPhase phase = PodPhase.PENDING;

        Pod(String image, String replicaSetId) {
            this.image = image;
            this.replicaSetId = replicaSetId;
        }

        String id() {
            return id;
        }

        String image() {
            return image;
        }

        PodPhase phase() {
            return phase;
        }

        void transition(PodPhase next) {
            Map<PodPhase, Set<PodPhase>> transitions = Map.of(
                PodPhase.PENDING,
                EnumSet.of(
                    PodPhase.RUNNING,
                    PodPhase.FAILED,
                    PodPhase.TERMINATING
                ),
                PodPhase.RUNNING,
                EnumSet.of(
                    PodPhase.READY,
                    PodPhase.FAILED,
                    PodPhase.TERMINATING
                ),
                PodPhase.READY,
                EnumSet.of(
                    PodPhase.FAILED,
                    PodPhase.TERMINATING
                ),
                PodPhase.FAILED,
                EnumSet.noneOf(PodPhase.class),
                PodPhase.TERMINATING,
                EnumSet.noneOf(PodPhase.class)
            );

            if (!transitions.get(phase).contains(next)) {
                throw new DeploymentException(
                    "Invalid Pod transition: " + phase + " -> " + next
                );
            }

            phase = next;
        }
    }

    static class ReplicaSet {
        private final String id = UUID.randomUUID().toString();
        private final int revision;
        private final String image;
        private final Map<String, Pod> pods = new HashMap<>();
        private int desiredReplicas;

        ReplicaSet(int revision, String image) {
            this.revision = revision;
            this.image = image;
        }

        String id() {
            return id;
        }

        int revision() {
            return revision;
        }

        String image() {
            return image;
        }

        int activeReplicas() {
            return (int) pods.values().stream()
                .filter(p -> EnumSet.of(
                    PodPhase.PENDING,
                    PodPhase.RUNNING,
                    PodPhase.READY
                ).contains(p.phase()))
                .count();
        }

        int readyReplicas() {
            return (int) pods.values().stream()
                .filter(p -> p.phase() == PodPhase.READY)
                .count();
        }

        Pod createPod() {
            Pod pod = new Pod(image, id);
            pods.put(pod.id(), pod);
            return pod;
        }

        void removePod(String podId) {
            Pod pod = pods.get(podId);

            if (pod == null) {
                throw new DeploymentException("Pod not found");
            }

            if (pod.phase() != PodPhase.TERMINATING) {
                pod.transition(PodPhase.TERMINATING);
            }

            pods.remove(podId);
        }
    }

    static class Deployment {
        private DeploymentSpec spec;
        private int revision;
        private DeploymentPhase phase = DeploymentPhase.PROGRESSING;
        private boolean paused;

        private final Map<String, ReplicaSet> replicaSets = new HashMap<>();
        private final List<RevisionRecord> history = new ArrayList<>();
        private final List<String> conditions = new ArrayList<>();

        Deployment(DeploymentSpec spec) {
            this.spec = spec;
        }

        String key() {
            return spec.namespace() + "/" + spec.name();
        }

        int readyReplicas() {
            return replicaSets.values().stream()
                .mapToInt(ReplicaSet::readyReplicas)
                .sum();
        }

        int totalReplicas() {
            return replicaSets.values().stream()
                .mapToInt(ReplicaSet::activeReplicas)
                .sum();
        }

        ReplicaSet currentReplicaSet() {
            return replicaSets.values().stream()
                .max(Comparator.comparingInt(ReplicaSet::revision))
                .orElseThrow(() ->
                    new DeploymentException("No ReplicaSet exists")
                );
        }
    }

    interface DeploymentPolicy {
        List<String> violations(DeploymentSpec spec);
    }

    static class ProductionPolicy implements DeploymentPolicy {
        private final int maximumReplicas;
        private final Set<String> approvedRegistries;

        ProductionPolicy(
            int maximumReplicas,
            Set<String> approvedRegistries
        ) {
            if (maximumReplicas < 0) {
                throw new IllegalArgumentException(
                    "Maximum replicas cannot be negative"
                );
            }

            this.maximumReplicas = maximumReplicas;
            this.approvedRegistries = Set.copyOf(approvedRegistries);
        }

        @Override
        public List<String> violations(DeploymentSpec spec) {
            List<String> errors = new ArrayList<>();

            if (spec.replicas() > maximumReplicas) {
                errors.add("Replica limit exceeded");
            }

            String registry = spec.container().image().split("/")[0];

            if (!approvedRegistries.contains(registry)) {
                errors.add("Unapproved container registry");
            }

            return List.copyOf(errors);
        }
    }

    static class DeploymentService {
        private final Map<String, Deployment> deployments = new HashMap<>();
        private final List<AuditEvent> auditEvents = new ArrayList<>();
        private final DeploymentPolicy policy;

        DeploymentService(DeploymentPolicy policy) {
            this.policy = Objects.requireNonNull(policy);
        }

        private void audit(Deployment deployment, String event, String details) {
            auditEvents.add(new AuditEvent(
                deployment.key(),
                event,
                details,
                Instant.now()
            ));
        }

        private void validatePolicy(DeploymentSpec spec) {
            List<String> violations = policy.violations(spec);

            if (!violations.isEmpty()) {
                throw new ValidationException(
                    String.join("; ", violations)
                );
            }
        }

        private ReplicaSet createRevision(
            Deployment deployment,
            String image
        ) {
            int revision = ++deployment.revision;

            ReplicaSet rs = new ReplicaSet(revision, image);

            deployment.replicaSets.put(rs.id(), rs);

            deployment.history.add(
                new RevisionRecord(revision, image, Instant.now())
            );

            while (
                deployment.history.size() >
                deployment.spec.revisionHistoryLimit()
            ) {
                deployment.history.remove(0);
            }

            audit(
                deployment,
                "REVISION_CREATED",
                "Revision " + revision + " image " + image
            );

            return rs;
        }

        Deployment create(DeploymentSpec spec) {
            validatePolicy(spec);

            Deployment deployment = new Deployment(spec);

            if (deployments.containsKey(deployment.key())) {
                throw new DeploymentException(
                    "Deployment already exists"
                );
            }

            deployments.put(deployment.key(), deployment);
            createRevision(deployment, spec.container().image());

            audit(deployment, "DEPLOYMENT_CREATED", spec.toString());
            reconcile(deployment);

            return deployment;
        }

        Deployment get(String name, String namespace) {
            Deployment deployment = deployments.get(
                namespace + "/" + name
            );

            if (deployment == null) {
                throw new DeploymentException("Deployment not found");
            }

            return deployment;
        }

        void reconcile(Deployment deployment) {
            if (deployment.paused) {
                deployment.phase = DeploymentPhase.PAUSED;
                return;
            }

            ReplicaSet current = deployment.currentReplicaSet();

            int desired = deployment.spec.replicas();
            int surgeLimit = desired + deployment.spec.maxSurge();

            current.desiredReplicas = desired;

            List<ReplicaSet> oldSets = deployment.replicaSets.values()
                .stream()
                .filter(rs -> !rs.id().equals(current.id()))
                .sorted(Comparator.comparingInt(ReplicaSet::revision))
                .toList();

            oldSets.forEach(rs -> rs.desiredReplicas = 0);

            int capacity = Math.max(
                0,
                surgeLimit - deployment.totalReplicas()
            );

            int missing = Math.max(
                0,
                desired - current.activeReplicas()
            );

            int scaleUp = Math.min(capacity, missing);

            for (int i = 0; i < scaleUp; i++) {
                current.createPod();
            }

            if (scaleUp > 0) {
                audit(
                    deployment,
                    "SCALE_UP",
                    "Created " + scaleUp + " Pods"
                );
            }

            int minimumAvailable = Math.max(
                0,
                desired - deployment.spec.maxUnavailable()
            );

            for (ReplicaSet old : oldSets) {
                List<String> candidates = old.pods.values().stream()
                    .sorted(Comparator.comparingInt(
                        pod -> pod.phase() == PodPhase.PENDING ? 0 : 1
                    ))
                    .map(Pod::id)
                    .toList();

                for (String podId : candidates) {
                    Pod pod = old.pods.get(podId);

                    if (pod == null) {
                        continue;
                    }

                    if (
                        pod.phase() == PodPhase.READY &&
                        deployment.readyReplicas() - 1 < minimumAvailable
                    ) {
                        continue;
                    }

                    old.removePod(podId);

                    audit(
                        deployment,
                        "OLD_POD_REMOVED",
                        podId
                    );
                }
            }

            updateStatus(deployment);
        }

        private void updateStatus(Deployment deployment) {
            if (deployment.spec.replicas() == 0) {
                deployment.phase = DeploymentPhase.AVAILABLE;
                return;
            }

            deployment.phase =
                deployment.readyReplicas() >= deployment.spec.replicas()
                    ? DeploymentPhase.AVAILABLE
                    : DeploymentPhase.PROGRESSING;
        }

        void completePendingPods(
            Deployment deployment,
            Set<String> failingImages
        ) {
            for (ReplicaSet rs : deployment.replicaSets.values()) {
                List<String> removeIds = new ArrayList<>();

                for (Pod pod : rs.pods.values()) {
                    if (pod.phase() != PodPhase.PENDING) {
                        continue;
                    }

                    if (failingImages.contains(pod.image())) {
                        pod.transition(PodPhase.FAILED);
                        removeIds.add(pod.id());

                        audit(
                            deployment,
                            "POD_START_FAILED",
                            pod.image()
                        );
                    } else {
                        pod.transition(PodPhase.RUNNING);
                        pod.transition(PodPhase.READY);

                        audit(
                            deployment,
                            "POD_READY",
                            pod.id()
                        );
                    }
                }

                removeIds.forEach(rs.pods::remove);
            }

            reconcile(deployment);
        }

        void completePendingPods(Deployment deployment) {
            completePendingPods(deployment, Set.of());
        }

        Deployment updateImage(
            String name,
            String namespace,
            String image
        ) {
            Deployment deployment = get(name, namespace);

            DeploymentSpec candidate = deployment.spec.withImage(image);
            validatePolicy(candidate);

            boolean changed = !candidate.container().image().equals(
                deployment.spec.container().image()
            );

            deployment.spec = candidate;

            if (changed) {
                createRevision(deployment, image);
            }

            audit(deployment, "SPEC_UPDATED", candidate.toString());
            reconcile(deployment);

            return deployment;
        }

        Deployment scale(
            String name,
            String namespace,
            int replicas
        ) {
            Deployment deployment = get(name, namespace);

            DeploymentSpec candidate =
                deployment.spec.withReplicas(replicas);

            validatePolicy(candidate);
            deployment.spec = candidate;

            audit(
                deployment,
                "SCALED",
                "Desired replicas: " + replicas
            );

            reconcile(deployment);
            return deployment;
        }

        Deployment rollingUpdate(
            String name,
            String namespace,
            String image,
            int maximumSteps
        ) {
            Deployment deployment = updateImage(
                name,
                namespace,
                image
            );

            for (int step = 0; step < maximumSteps; step++) {
                completePendingPods(deployment);

                ReplicaSet current = deployment.currentReplicaSet();

                int oldActive = deployment.replicaSets.values().stream()
                    .filter(rs -> !rs.id().equals(current.id()))
                    .mapToInt(ReplicaSet::activeReplicas)
                    .sum();

                if (
                    current.readyReplicas() == deployment.spec.replicas()
                    && oldActive == 0
                ) {
                    deployment.phase = DeploymentPhase.AVAILABLE;

                    audit(
                        deployment,
                        "ROLLOUT_COMPLETED",
                        image
                    );

                    return deployment;
                }

                reconcile(deployment);
            }

            deployment.phase = DeploymentPhase.DEGRADED;

            throw new DeploymentException(
                "Rolling update exceeded maximum steps"
            );
        }

        Deployment rollback(
            String name,
            String namespace,
            Optional<Integer> targetRevision
        ) {
            Deployment deployment = get(name, namespace);

            ReplicaSet target = deployment.replicaSets.values().stream()
                .filter(rs -> rs.revision() < deployment.revision)
                .filter(rs ->
                    targetRevision.isEmpty() ||
                    rs.revision() == targetRevision.get()
                )
                .max(Comparator.comparingInt(ReplicaSet::revision))
                .orElseThrow(() ->
                    new DeploymentException(
                        "Historical revision not found"
                    )
                );

            DeploymentSpec candidate =
                deployment.spec.withImage(target.image());

            validatePolicy(candidate);

            deployment.spec = candidate;

            // A rollback creates a new revision using the older image.
            createRevision(deployment, target.image());

            audit(
                deployment,
                "ROLLBACK_STARTED",
                "Target revision " + target.revision()
            );

            reconcile(deployment);
            return deployment;
        }

        void pause(String name, String namespace) {
            Deployment deployment = get(name, namespace);
            deployment.paused = true;
            deployment.phase = DeploymentPhase.PAUSED;
            audit(deployment, "PAUSED", "");
        }

        void resume(String name, String namespace) {
            Deployment deployment = get(name, namespace);
            deployment.paused = false;
            audit(deployment, "RESUMED", "");
            reconcile(deployment);
        }

        List<AuditEvent> auditEvents() {
            return List.copyOf(auditEvents);
        }

        void printReport(Deployment deployment) {
            System.out.println("\nDeployment: " + deployment.key());
            System.out.println("Image: " + deployment.spec.container().image());
            System.out.println("Desired: " + deployment.spec.replicas());
            System.out.println("Ready: " + deployment.readyReplicas());
            System.out.println("Active: " + deployment.totalReplicas());
            System.out.println("Revision: " + deployment.revision);
            System.out.println("Phase: " + deployment.phase);

            deployment.replicaSets.values().stream()
                .sorted(Comparator.comparingInt(ReplicaSet::revision))
                .forEach(rs -> System.out.printf(
                    "Revision=%d image=%s desired=%d active=%d ready=%d%n",
                    rs.revision(),
                    rs.image(),
                    rs.desiredReplicas,
                    rs.activeReplicas(),
                    rs.readyReplicas()
                ));
        }
    }

    private static void runTests() {
        ProductionPolicy policy = new ProductionPolicy(
            10,
            Set.of("registry.example.com")
        );

        DeploymentService service = new DeploymentService(policy);

        DeploymentSpec spec = new DeploymentSpec(
            "orders-api",
            "production",
            3,
            new ContainerSpec(
                "orders",
                "registry.example.com/orders:v1",
                8080,
                "100m",
                "128Mi"
            ),
            1,
            0,
            5
        );

        Deployment deployment = service.create(spec);

        service.completePendingPods(deployment);

        if (deployment.readyReplicas() != 3) {
            throw new AssertionError("Initial replicas failed");
        }

        service.rollingUpdate(
            "orders-api",
            "production",
            "registry.example.com/orders:v2",
            100
        );

        if (!deployment.spec.container().image().endsWith(":v2")) {
            throw new AssertionError("Update failed");
        }

        service.rollback(
            "orders-api",
            "production",
            Optional.of(1)
        );

        service.completePendingPods(deployment);

        if (!deployment.spec.container().image().endsWith(":v1")) {
            throw new AssertionError("Rollback failed");
        }

        service.scale("orders-api", "production", 5);
        service.completePendingPods(deployment);

        if (deployment.readyReplicas() != 5) {
            throw new AssertionError("Scaling failed");
        }

        try {
            service.scale("orders-api", "production", 11);
            throw new AssertionError("Policy violation accepted");
        } catch (ValidationException expected) {
            // Expected policy rejection.
        }

        try {
            service.scale("orders-api", "production", -1);
            throw new AssertionError("Negative replicas accepted");
        } catch (ValidationException expected) {
            // Expected input rejection.
        }

        service.pause("orders-api", "production");

        if (deployment.phase != DeploymentPhase.PAUSED) {
            throw new AssertionError("Pause failed");
        }

        service.resume("orders-api", "production");

        System.out.println("All Java 17 tests passed.");
        service.printReport(deployment);
    }

    public static void main(String[] args) {
        try {
            ProductionPolicy policy = new ProductionPolicy(
                20,
                Set.of("registry.example.com")
            );

            DeploymentService service = new DeploymentService(policy);

            DeploymentSpec spec = new DeploymentSpec(
                "payment-service",
                "production",
                3,
                new ContainerSpec(
                    "payment",
                    "registry.example.com/payment:v1",
                    8080,
                    "200m",
                    "256Mi"
                ),
                1,
                0,
                5
            );

            Deployment deployment = service.create(spec);
            service.completePendingPods(deployment);

            System.out.println("Initial deployment");
            service.printReport(deployment);

            System.out.println("\nRolling update");
            service.rollingUpdate(
                "payment-service",
                "production",
                "registry.example.com/payment:v2",
                100
            );
            service.printReport(deployment);

            System.out.println("\nRollback");
            service.rollback(
                "payment-service",
                "production",
                Optional.of(1)
            );
            service.completePendingPods(deployment);
            service.printReport(deployment);

            runTests();

        } catch (DeploymentException exception) {
            System.err.println(
                "Deployment operation failed: " + exception.getMessage()
            );
            System.exitCode = 1;
        }
    }
}
