import java.time.Instant;
import java.util.*;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Collectors;

/*
 * Kubernetes Control Plane
 *
 * Enterprise-oriented cluster management model.
 *
 * Includes:
 * - API server
 * - Versioned cluster-state repository
 * - Resource validation
 * - Scheduler and node allocation
 * - Deployment controller
 * - Reconciliation services
 * - Event auditing
 * - Optimistic concurrency
 * - Failure classification
 *
 * Java 17
 * No third-party dependencies.
 */

public class KubernetesControlPlane {

    // ========================================================
    // ENUMS
    // ========================================================

    enum PodPhase {
        PENDING,
        RUNNING,
        FAILED,
        SUCCEEDED
    }

    enum NodeCondition {
        READY,
        NOT_READY
    }

    enum ResourceType {
        NODE,
        POD,
        DEPLOYMENT
    }

    enum AuditAction {
        CREATE,
        UPDATE,
        DELETE
    }


    // ========================================================
    // EXCEPTIONS
    // ========================================================

    static class ControlPlaneException
            extends RuntimeException {

        ControlPlaneException(String message) {
            super(message);
        }
    }

    static class ValidationException
            extends ControlPlaneException {

        ValidationException(String message) {
            super(message);
        }
    }

    static class ResourceConflictException
            extends ControlPlaneException {

        ResourceConflictException(String message) {
            super(message);
        }
    }

    static class ResourceNotFoundException
            extends ControlPlaneException {

        ResourceNotFoundException(String message) {
            super(message);
        }
    }

    static class SchedulingException
            extends ControlPlaneException {

        SchedulingException(String message) {
            super(message);
        }
    }


    // ========================================================
    // DOMAIN INTERFACE
    // ========================================================

    interface ClusterResource {

        String name();

        String namespace();

        String uid();

        long resourceVersion();

        ClusterResource withVersion(long version);
    }


    // ========================================================
    // RESOURCE MODELS
    // ========================================================

    record ResourceMetadata(
            String name,
            String namespace,
            String uid,
            long resourceVersion,
            Map<String, String> labels
    ) {

        ResourceMetadata {
            validateName(name);
            validateName(namespace);

            if (uid == null || uid.isBlank()) {
                throw new ValidationException("UID required");
            }

            labels = Map.copyOf(labels);
        }

        ResourceMetadata withVersion(long version) {
            return new ResourceMetadata(
                    name,
                    namespace,
                    uid,
                    version,
                    labels
            );
        }
    }


    record Node(
            ResourceMetadata metadata,
            int cpuCapacity,
            int memoryCapacity,
            int cpuUsed,
            int memoryUsed,
            NodeCondition condition
    ) implements ClusterResource {

        Node {
            if (
                    cpuCapacity <= 0 ||
                    memoryCapacity <= 0 ||
                    cpuUsed < 0 ||
                    memoryUsed < 0 ||
                    cpuUsed > cpuCapacity ||
                    memoryUsed > memoryCapacity
            ) {
                throw new ValidationException(
                        "Invalid node resource allocation"
                );
            }

            Objects.requireNonNull(condition);
        }

        int availableCpu() {
            return cpuCapacity - cpuUsed;
        }

        int availableMemory() {
            return memoryCapacity - memoryUsed;
        }

        Node allocate(int cpu, int memory) {

            if (
                    cpu > availableCpu() ||
                    memory > availableMemory()
            ) {
                throw new SchedulingException(
                        "Node capacity exceeded"
                );
            }

            return new Node(
                    metadata,
                    cpuCapacity,
                    memoryCapacity,
                    cpuUsed + cpu,
                    memoryUsed + memory,
                    condition
            );
        }

        Node release(int cpu, int memory) {

            return new Node(
                    metadata,
                    cpuCapacity,
                    memoryCapacity,
                    Math.max(0, cpuUsed - cpu),
                    Math.max(0, memoryUsed - memory),
                    condition
            );
        }

        @Override
        public String name() {
            return metadata.name();
        }

        @Override
        public String namespace() {
            return metadata.namespace();
        }

        @Override
        public String uid() {
            return metadata.uid();
        }

        @Override
        public long resourceVersion() {
            return metadata.resourceVersion();
        }

        @Override
        public Node withVersion(long version) {
            return new Node(
                    metadata.withVersion(version),
                    cpuCapacity,
                    memoryCapacity,
                    cpuUsed,
                    memoryUsed,
                    condition
            );
        }
    }


    record Pod(
            ResourceMetadata metadata,
            String image,
            int cpuRequest,
            int memoryRequest,
            String ownerUid,
            String nodeName,
            PodPhase phase
    ) implements ClusterResource {

        Pod {
            Objects.requireNonNull(image);
            Objects.requireNonNull(phase);

            if (
                    image.isBlank() ||
                    cpuRequest <= 0 ||
                    memoryRequest <= 0
            ) {
                throw new ValidationException(
                        "Invalid Pod specification"
                );
            }
        }

        Pod bind(String node) {
            return new Pod(
                    metadata,
                    image,
                    cpuRequest,
                    memoryRequest,
                    ownerUid,
                    node,
                    PodPhase.RUNNING
            );
        }

        @Override
        public String name() {
            return metadata.name();
        }

        @Override
        public String namespace() {
            return metadata.namespace();
        }

        @Override
        public String uid() {
            return metadata.uid();
        }

        @Override
        public long resourceVersion() {
            return metadata.resourceVersion();
        }

        @Override
        public Pod withVersion(long version) {
            return new Pod(
                    metadata.withVersion(version),
                    image,
                    cpuRequest,
                    memoryRequest,
                    ownerUid,
                    nodeName,
                    phase
            );
        }
    }


    record Deployment(
            ResourceMetadata metadata,
            int desiredReplicas,
            String image,
            int cpuRequest,
            int memoryRequest,
            Map<String, String> selector,
            long generation
    ) implements ClusterResource {

        Deployment {
            if (
                    desiredReplicas < 0 ||
                    desiredReplicas > 10000 ||
                    cpuRequest <= 0 ||
                    memoryRequest <= 0 ||
                    image == null ||
                    image.isBlank() ||
                    selector.isEmpty()
            ) {
                throw new ValidationException(
                        "Invalid Deployment specification"
                );
            }

            selector = Map.copyOf(selector);
        }

        @Override
        public String name() {
            return metadata.name();
        }

        @Override
        public String namespace() {
            return metadata.namespace();
        }

        @Override
        public String uid() {
            return metadata.uid();
        }

        @Override
        public long resourceVersion() {
            return metadata.resourceVersion();
        }

        @Override
        public Deployment withVersion(long version) {
            return new Deployment(
                    metadata.withVersion(version),
                    desiredReplicas,
                    image,
                    cpuRequest,
                    memoryRequest,
                    selector,
                    generation
            );
        }
    }


    // ========================================================
    // VALIDATION
    // ========================================================

    static void validateName(String name) {

        if (
                name == null ||
                !name.matches(
                        "[a-z0-9]([-a-z0-9]*[a-z0-9])?"
                ) ||
                name.length() > 253
        ) {
            throw new ValidationException(
                    "Invalid Kubernetes resource name"
            );
        }
    }


    // ========================================================
    // AUDIT MODEL
    // ========================================================

    record AuditEvent(
            AuditAction action,
            ResourceType type,
            String resourceName,
            long revision,
            Instant timestamp
    ) {}


    // ========================================================
    // CLUSTER STATE REPOSITORY
    // ========================================================

    static class ClusterStateRepository {

        private final Map<String, ClusterResource> objects =
                new HashMap<>();

        private final AtomicLong revision =
                new AtomicLong();

        private final List<AuditEvent> audit =
                new ArrayList<>();

        private String key(
                ResourceType type,
                ClusterResource resource
        ) {
            return type.name().toLowerCase()
                    + "/" + resource.namespace()
                    + "/" + resource.name();
        }

        synchronized <T extends ClusterResource> T create(
                ResourceType type,
                T resource
        ) {

            String key = key(type, resource);

            if (objects.containsKey(key)) {
                throw new ResourceConflictException(
                        "Resource already exists: " + key
                );
            }

            return save(type, key, resource, 0);
        }

        synchronized <T extends ClusterResource> T update(
                ResourceType type,
                T resource,
                long expectedVersion
        ) {

            String key = key(type, resource);

            ClusterResource current = objects.get(key);

            if (current == null) {
                throw new ResourceNotFoundException(key);
            }

            if (
                    current.resourceVersion() !=
                    expectedVersion
            ) {
                throw new ResourceConflictException(
                        "Stale resource version"
                );
            }

            return save(
                    type,
                    key,
                    resource,
                    expectedVersion
            );
        }

        private <T extends ClusterResource> T save(
                ResourceType type,
                String key,
                T resource,
                long expectedVersion
        ) {

            long newVersion = revision.incrementAndGet();

            @SuppressWarnings("unchecked")
            T saved = (T) resource.withVersion(newVersion);

            objects.put(key, saved);

            audit.add(new AuditEvent(
                    objects.containsKey(key)
                            ? AuditAction.UPDATE
                            : AuditAction.CREATE,
                    type,
                    resource.name(),
                    newVersion,
                    Instant.now()
            ));

            return saved;
        }

        synchronized <T extends ClusterResource> T get(
                ResourceType type,
                String namespace,
                String name,
                Class<T> expectedType
        ) {

            String key = type.name().toLowerCase()
                    + "/" + namespace + "/" + name;

            ClusterResource resource = objects.get(key);

            if (resource == null) {
                throw new ResourceNotFoundException(key);
            }

            return expectedType.cast(resource);
        }

        synchronized <T extends ClusterResource> List<T> list(
                ResourceType type,
                Class<T> expectedType
        ) {

            String prefix = type.name().toLowerCase() + "/";

            return objects.entrySet().stream()
                    .filter(entry ->
                            entry.getKey().startsWith(prefix))
                    .map(Map.Entry::getValue)
                    .map(expectedType::cast)
                    .toList();
        }

        synchronized void delete(
                ResourceType type,
                ClusterResource resource,
                long expectedVersion
        ) {

            String key = key(type, resource);

            ClusterResource current = objects.get(key);

            if (current == null) {
                throw new ResourceNotFoundException(key);
            }

            if (
                    current.resourceVersion() !=
                    expectedVersion
            ) {
                throw new ResourceConflictException(
                        "Delete version conflict"
                );
            }

            objects.remove(key);

            long newVersion = revision.incrementAndGet();

            audit.add(new AuditEvent(
                    AuditAction.DELETE,
                    type,
                    resource.name(),
                    newVersion,
                    Instant.now()
            ));
        }

        long revision() {
            return revision.get();
        }

        List<AuditEvent> auditEvents() {
            return List.copyOf(audit);
        }
    }


    // ========================================================
    // API SERVER
    // ========================================================

    static class ApiServer {

        private final ClusterStateRepository repository;

        ApiServer(ClusterStateRepository repository) {
            this.repository = repository;
        }

        Node createNode(Node node) {
            return repository.create(
                    ResourceType.NODE,
                    node
            );
        }

        Pod createPod(Pod pod) {
            return repository.create(
                    ResourceType.POD,
                    pod
            );
        }

        Deployment createDeployment(Deployment deployment) {
            return repository.create(
                    ResourceType.DEPLOYMENT,
                    deployment
            );
        }

        Node updateNode(Node node) {
            return repository.update(
                    ResourceType.NODE,
                    node,
                    node.resourceVersion()
            );
        }

        Pod updatePod(Pod pod) {
            return repository.update(
                    ResourceType.POD,
                    pod,
                    pod.resourceVersion()
            );
        }

        Node getNode(String name) {
            return repository.get(
                    ResourceType.NODE,
                    "default",
                    name,
                    Node.class
            );
        }

        List<Node> nodes() {
            return repository.list(
                    ResourceType.NODE,
                    Node.class
            );
        }

        List<Pod> pods() {
            return repository.list(
                    ResourceType.POD,
                    Pod.class
            );
        }

        List<Deployment> deployments() {
            return repository.list(
                    ResourceType.DEPLOYMENT,
                    Deployment.class
            );
        }

        void deletePod(Pod pod) {
            repository.delete(
                    ResourceType.POD,
                    pod,
                    pod.resourceVersion()
            );
        }

        long revision() {
            return repository.revision();
        }
    }


    // ========================================================
    // SCHEDULING POLICY
    // ========================================================

    interface SchedulingPolicy {

        Optional<Node> selectNode(
                Pod pod,
                List<Node> candidates
        );
    }


    static class ResourceAwareSchedulingPolicy
            implements SchedulingPolicy {

        @Override
        public Optional<Node> selectNode(
                Pod pod,
                List<Node> candidates
        ) {

            return candidates.stream()
                    .filter(node ->
                            node.condition() == NodeCondition.READY)
                    .filter(node ->
                            node.availableCpu() >= pod.cpuRequest())
                    .filter(node ->
                            node.availableMemory() >=
                                    pod.memoryRequest())
                    .max(
                            Comparator.comparingInt(
                                    Node::availableCpu
                            ).thenComparingInt(
                                    Node::availableMemory
                            )
                    );
        }
    }


    // ========================================================
    // SCHEDULER SERVICE
    // ========================================================

    static class SchedulerService {

        private final ApiServer api;
        private final SchedulingPolicy policy;

        SchedulerService(
                ApiServer api,
                SchedulingPolicy policy
        ) {
            this.api = api;
            this.policy = policy;
        }

        boolean schedule(Pod pod) {

            Optional<Node> selected = policy.selectNode(
                    pod,
                    api.nodes()
            );

            if (selected.isEmpty()) {
                return false;
            }

            Node node = selected.get();

            Node allocated = node.allocate(
                    pod.cpuRequest(),
                    pod.memoryRequest()
            );

            // Persist resource reservation before Pod binding.
            api.updateNode(allocated);

            api.updatePod(pod.bind(node.name()));

            return true;
        }
    }


    // ========================================================
    // RECONCILIATION RESULT
    // ========================================================

    record ReconciliationResult(
            String deployment,
            int desired,
            int running,
            int created,
            int removed
    ) {}


    // ========================================================
    // DEPLOYMENT CONTROLLER
    // ========================================================

    static class DeploymentController {

        private final ApiServer api;
        private final AtomicLong sequence =
                new AtomicLong();

        DeploymentController(ApiServer api) {
            this.api = api;
        }

        private boolean matches(
                Pod pod,
                Deployment deployment
        ) {

            return pod.ownerUid().equals(deployment.uid())
                    && deployment.selector().entrySet()
                    .stream()
                    .allMatch(entry ->
                            Objects.equals(
                                    pod.metadata().labels()
                                            .get(entry.getKey()),
                                    entry.getValue()
                            )
                    );
        }

        private void release(Pod pod) {

            if (pod.nodeName() == null) {
                return;
            }

            Node node = api.getNode(pod.nodeName());

            api.updateNode(
                    node.release(
                            pod.cpuRequest(),
                            pod.memoryRequest()
                    )
            );
        }

        ReconciliationResult reconcile(
                Deployment deployment
        ) {

            List<Pod> owned = api.pods().stream()
                    .filter(pod ->
                            matches(pod, deployment))
                    .toList();

            int running = (int) owned.stream()
                    .filter(pod ->
                            pod.phase() == PodPhase.RUNNING)
                    .count();

            int missing = Math.max(
                    0,
                    deployment.desiredReplicas() - running
            );

            int excess = Math.max(
                    0,
                    owned.size() - deployment.desiredReplicas()
            );

            int removed = 0;

            for (Pod pod : owned.stream()
                    .sorted(Comparator.comparing(Pod::name))
                    .limit(excess)
                    .toList()) {

                release(pod);
                api.deletePod(pod);
                removed++;
            }

            int created = 0;

            for (int i = 0; i < missing; i++) {

                long id = sequence.incrementAndGet();

                ResourceMetadata metadata =
                        new ResourceMetadata(
                                deployment.name() + "-" + id,
                                deployment.namespace(),
                                UUID.randomUUID().toString(),
                                0,
                                deployment.selector()
                        );

                Pod pod = new Pod(
                        metadata,
                        deployment.image(),
                        deployment.cpuRequest(),
                        deployment.memoryRequest(),
                        deployment.uid(),
                        null,
                        PodPhase.PENDING
                );

                api.createPod(pod);
                created++;
            }

            return new ReconciliationResult(
                    deployment.name(),
                    deployment.desiredReplicas(),
                    running,
                    created,
                    removed
            );
        }
    }


    // ========================================================
    // CONTROL PLANE SERVICE
    // ========================================================

    static class ControlPlaneService {

        private final ClusterStateRepository repository;
        private final ApiServer api;
        private final SchedulerService scheduler;
        private final DeploymentController controller;

        ControlPlaneService() {

            repository = new ClusterStateRepository();
            api = new ApiServer(repository);

            scheduler = new SchedulerService(
                    api,
                    new ResourceAwareSchedulingPolicy()
            );

            controller = new DeploymentController(api);
        }

        void addNode(
                String name,
                int cpu,
                int memory
        ) {

            ResourceMetadata metadata =
                    new ResourceMetadata(
                            name,
                            "default",
                            UUID.randomUUID().toString(),
                            0,
                            Map.of("role", "worker")
                    );

            api.createNode(new Node(
                    metadata,
                    cpu,
                    memory,
                    0,
                    0,
                    NodeCondition.READY
            ));
        }

        void deploy(Deployment deployment) {
            api.createDeployment(deployment);
        }

        void reconcile() {

            for (Deployment deployment : api.deployments()) {

                ReconciliationResult result =
                        controller.reconcile(deployment);

                System.out.println(
                        "RECONCILIATION: " + result
                );
            }

            // Re-read Pods after controller operations.
            for (Pod pod : api.pods()) {

                if (pod.phase() != PodPhase.PENDING) {
                    continue;
                }

                try {

                    boolean scheduled =
                            scheduler.schedule(pod);

                    if (!scheduled) {
                        System.out.println(
                                "UNSCHEDULABLE: " + pod.name()
                        );
                    }

                } catch (ResourceConflictException error) {

                    System.out.println(
                            "CONCURRENT UPDATE: " +
                            error.getMessage()
                    );
                }
            }
        }

        void report() {

            System.out.println("\nNODES");

            api.nodes().forEach(node ->
                    System.out.printf(
                            "%s CPU %d/%d MEMORY %d/%d%n",
                            node.name(),
                            node.cpuUsed(),
                            node.cpuCapacity(),
                            node.memoryUsed(),
                            node.memoryCapacity()
                    )
            );

            System.out.println("\nPODS");

            api.pods().forEach(pod ->
                    System.out.printf(
                            "%s %s %s%n",
                            pod.name(),
                            pod.phase(),
                            Objects.toString(
                                    pod.nodeName(),
                                    "Unassigned"
                            )
                    )
            );

            System.out.println(
                    "\nCLUSTER REVISION: " + api.revision()
            );

            System.out.println(
                    "AUDIT EVENTS: " +
                    repository.auditEvents().size()
            );
        }

        ApiServer api() {
            return api;
        }
    }


    // ========================================================
    // APPLICATION ENTRY POINT
    // ========================================================

    public static void main(String[] args) {

        try {

            ControlPlaneService cluster =
                    new ControlPlaneService();

            cluster.addNode("worker-01", 8, 16384);
            cluster.addNode("worker-02", 4, 8192);

            ResourceMetadata metadata =
                    new ResourceMetadata(
                            "customer-api",
                            "default",
                            "deployment-customer-001",
                            0,
                            Map.of("app", "customer")
                    );

            Deployment deployment = new Deployment(
                    metadata,
                    5,
                    "customer-api:2.4",
                    1,
                    512,
                    Map.of("app", "customer"),
                    1
            );

            cluster.deploy(deployment);

            System.out.println(
                    "\nFIRST RECONCILIATION"
            );

            cluster.reconcile();

            System.out.println(
                    "\nSECOND RECONCILIATION"
            );

            cluster.reconcile();

            cluster.report();

            // Demonstrate stale resource-version rejection.
            Node node = cluster.api().getNode("worker-01");

            try {

                Node stale = node.withVersion(0);

                cluster.api().updateNode(stale);

            } catch (ResourceConflictException error) {

                System.out.println(
                        "\nEXPECTED CONFLICT: " +
                        error.getMessage()
                );
            }

            // Demonstrate invalid replica count.
            try {

                new Deployment(
                        metadata,
                        -1,
                        "invalid:1",
                        1,
                        256,
                        Map.of("app", "invalid"),
                        1
                );

            } catch (ValidationException error) {

                System.out.println(
                        "\nVALIDATION FAILURE: " +
                        error.getMessage()
                );
            }

        } catch (ControlPlaneException error) {

            System.err.println(
                    "CONTROL PLANE ERROR: " +
                    error.getMessage()
            );

            System.exit(1);
        }
    }
}
