import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/*
 * Enterprise Kubernetes Pod Lifecycle and Governance Model.
 *
 * Java 17 standalone application.
 *
 * Covers:
 * - Immutable Pod specifications
 * - Container and init-container definitions
 * - Resource-aware scheduling
 * - Pod lifecycle transitions
 * - Readiness and liveness
 * - Restart policies
 * - Multi-container communication
 * - Graceful termination
 * - Domain validation and event reporting
 */

public class Pods {

    enum PodPhase {
        PENDING,
        RUNNING,
        SUCCEEDED,
        FAILED,
        UNKNOWN
    }

    enum ContainerState {
        WAITING,
        RUNNING,
        TERMINATED
    }

    enum RestartPolicy {
        ALWAYS,
        ON_FAILURE,
        NEVER
    }

    enum ConditionType {
        INITIALIZED,
        READY,
        POD_SCHEDULED
    }

    static class PodException extends RuntimeException {
        PodException(String message) {
            super(message);
        }
    }

    static class ResourceException extends PodException {
        ResourceException(String message) {
            super(message);
        }
    }

    record ResourceRequirements(
        int cpuMillicores,
        int memoryMiB
    ) {
        ResourceRequirements {
            if (cpuMillicores <= 0 || memoryMiB <= 0) {
                throw new IllegalArgumentException(
                    "Resource requirements must be positive"
                );
            }
        }
    }

    record ContainerDefinition(
        String name,
        String image,
        List<Integer> ports,
        ResourceRequirements resources,
        boolean essential
    ) {
        private static final Pattern NAME_PATTERN =
            Pattern.compile("[a-z0-9]([-a-z0-9]*[a-z0-9])?");

        ContainerDefinition {
            Objects.requireNonNull(name);
            Objects.requireNonNull(image);
            Objects.requireNonNull(resources);

            if (
                name.length() > 63 ||
                !NAME_PATTERN.matcher(name).matches()
            ) {
                throw new IllegalArgumentException(
                    "Invalid container name: " + name
                );
            }

            if (image.isBlank() || image.length() > 253) {
                throw new IllegalArgumentException("Invalid image");
            }

            ports = List.copyOf(ports);

            if (ports.stream().anyMatch(
                p -> p < 1 || p > 65535
            )) {
                throw new IllegalArgumentException("Invalid port");
            }
        }
    }

    record PodMetadata(
        String name,
        String namespace,
        Map<String, String> labels,
        Map<String, String> annotations
    ) {
        PodMetadata {
            Objects.requireNonNull(name);
            Objects.requireNonNull(namespace);

            if (name.isBlank() || namespace.isBlank()) {
                throw new IllegalArgumentException(
                    "Pod name and namespace are required"
                );
            }

            labels = Map.copyOf(labels);
            annotations = Map.copyOf(annotations);
        }
    }

    record PodSpec(
        List<ContainerDefinition> containers,
        List<ContainerDefinition> initContainers,
        RestartPolicy restartPolicy,
        int terminationGracePeriodSeconds,
        String serviceAccount
    ) {
        PodSpec {
            containers = List.copyOf(containers);
            initContainers = List.copyOf(initContainers);

            Objects.requireNonNull(restartPolicy);
            Objects.requireNonNull(serviceAccount);

            if (containers.isEmpty()) {
                throw new IllegalArgumentException(
                    "At least one application container is required"
                );
            }

            if (terminationGracePeriodSeconds < 0) {
                throw new IllegalArgumentException(
                    "Termination grace period cannot be negative"
                );
            }

            if (serviceAccount.isBlank()) {
                throw new IllegalArgumentException(
                    "Service account is required"
                );
            }

            Set<String> names = new HashSet<>();

            for (ContainerDefinition container : containers) {
                if (!names.add(container.name())) {
                    throw new IllegalArgumentException(
                        "Duplicate container name"
                    );
                }
            }

            for (ContainerDefinition container : initContainers) {
                if (!names.add(container.name())) {
                    throw new IllegalArgumentException(
                        "Duplicate container name"
                    );
                }
            }
        }

        ResourceRequirements scheduledResources() {
            int applicationCPU = containers.stream()
                .mapToInt(c -> c.resources().cpuMillicores())
                .sum();

            int applicationMemory = containers.stream()
                .mapToInt(c -> c.resources().memoryMiB())
                .sum();

            int initCPU = initContainers.stream()
                .mapToInt(c -> c.resources().cpuMillicores())
                .max()
                .orElse(0);

            int initMemory = initContainers.stream()
                .mapToInt(c -> c.resources().memoryMiB())
                .max()
                .orElse(0);

            // Simplified scheduling calculation for ordinary init containers.
            return new ResourceRequirements(
                Math.max(applicationCPU, initCPU),
                Math.max(applicationMemory, initMemory)
            );
        }
    }

    static class ContainerRuntime {
        private final ContainerDefinition definition;
        private ContainerState state = ContainerState.WAITING;
        private int restartCount;
        private Integer exitCode;
        private boolean ready;
        private boolean livenessHealthy = true;
        private boolean readinessHealthy = true;

        ContainerRuntime(ContainerDefinition definition) {
            this.definition = definition;
        }

        ContainerDefinition definition() {
            return definition;
        }

        ContainerState state() {
            return state;
        }

        int restartCount() {
            return restartCount;
        }

        boolean ready() {
            return ready;
        }

        void start() {
            if (state == ContainerState.RUNNING) {
                throw new PodException("Container already running");
            }

            state = ContainerState.RUNNING;
            exitCode = null;
            ready = readinessHealthy;
        }

        void terminate(int code) {
            if (state != ContainerState.RUNNING) {
                throw new PodException("Container is not running");
            }

            if (code < 0) {
                throw new IllegalArgumentException("Invalid exit code");
            }

            state = ContainerState.TERMINATED;
            exitCode = code;
            ready = false;
        }

        void restart() {
            restartCount++;
            start();
        }

        void setReadiness(boolean value) {
            if (state != ContainerState.RUNNING) {
                throw new PodException("Container is not running");
            }

            readinessHealthy = value;
            ready = value;
        }

        void setLivenessHealthy(boolean value) {
            livenessHealthy = value;
        }
    }

    static class PodAggregate {
        private final UUID id = UUID.randomUUID();
        private final PodMetadata metadata;
        private final PodSpec spec;
        private final Map<String, ContainerRuntime> applicationContainers =
            new HashMap<>();
        private final List<ContainerRuntime> initContainers =
            new ArrayList<>();
        private final Map<ConditionType, Boolean> conditions =
            new HashMap<>();
        private final List<String> events = new ArrayList<>();

        private PodPhase phase = PodPhase.PENDING;
        private String assignedNode;
        private boolean deleting;

        PodAggregate(PodMetadata metadata, PodSpec spec) {
            this.metadata = metadata;
            this.spec = spec;

            for (ContainerDefinition definition : spec.containers()) {
                applicationContainers.put(
                    definition.name(),
                    new ContainerRuntime(definition)
                );
            }

            for (ContainerDefinition definition : spec.initContainers()) {
                initContainers.add(new ContainerRuntime(definition));
            }

            conditions.put(ConditionType.INITIALIZED, false);
            conditions.put(ConditionType.READY, false);
            conditions.put(ConditionType.POD_SCHEDULED, false);

            record("Pod aggregate created");
        }

        UUID id() {
            return id;
        }

        String name() {
            return metadata.name();
        }

        String namespace() {
            return metadata.namespace();
        }

        PodSpec spec() {
            return spec;
        }

        PodPhase phase() {
            return phase;
        }

        Optional<String> assignedNode() {
            return Optional.ofNullable(assignedNode);
        }

        boolean ready() {
            return phase == PodPhase.RUNNING
                && Boolean.TRUE.equals(conditions.get(ConditionType.READY));
        }

        List<String> events() {
            return Collections.unmodifiableList(events);
        }

        ContainerRuntime container(String name) {
            ContainerRuntime runtime = applicationContainers.get(name);

            if (runtime == null) {
                throw new PodException("Unknown container: " + name);
            }

            return runtime;
        }

        void assignNode(String nodeName) {
            if (phase != PodPhase.PENDING || assignedNode != null) {
                throw new PodException("Pod cannot be scheduled");
            }

            assignedNode = nodeName;
            conditions.put(ConditionType.POD_SCHEDULED, true);
            record("Scheduled on " + nodeName);
        }

        void setPhase(PodPhase newPhase) {
            phase = newPhase;
            record("Phase changed to " + newPhase);
        }

        void updateReadinessCondition() {
            boolean allReady = !applicationContainers.isEmpty()
                && applicationContainers.values().stream().allMatch(
                    c -> c.state() == ContainerState.RUNNING && c.ready()
                );

            conditions.put(ConditionType.READY, allReady);
        }

        void record(String event) {
            String entry = Instant.now() + " " + event;
            events.add(entry);
            System.out.println("[" + name() + "] " + event);
        }

        void markInitialized() {
            conditions.put(ConditionType.INITIALIZED, true);
        }

        List<ContainerRuntime> applicationRuntimes() {
            return new ArrayList<>(applicationContainers.values());
        }
    }

    static class WorkerNode {
        private final String name;
        private final int cpuCapacity;
        private final int memoryCapacity;
        private int allocatedCPU;
        private int allocatedMemory;
        private final Set<UUID> assignedPods = new HashSet<>();

        WorkerNode(
            String name,
            int cpuCapacity,
            int memoryCapacity
        ) {
            if (
                name == null ||
                name.isBlank() ||
                cpuCapacity <= 0 ||
                memoryCapacity <= 0
            ) {
                throw new IllegalArgumentException(
                    "Invalid worker node"
                );
            }

            this.name = name;
            this.cpuCapacity = cpuCapacity;
            this.memoryCapacity = memoryCapacity;
        }

        String name() {
            return name;
        }

        boolean canFit(ResourceRequirements resources) {
            return allocatedCPU + resources.cpuMillicores()
                    <= cpuCapacity
                && allocatedMemory + resources.memoryMiB()
                    <= memoryCapacity;
        }

        void allocate(
            UUID podId,
            ResourceRequirements resources
        ) {
            if (assignedPods.contains(podId)) {
                throw new ResourceException("Pod already allocated");
            }

            if (!canFit(resources)) {
                throw new ResourceException("Insufficient node capacity");
            }

            allocatedCPU += resources.cpuMillicores();
            allocatedMemory += resources.memoryMiB();
            assignedPods.add(podId);
        }

        void release(
            UUID podId,
            ResourceRequirements resources
        ) {
            if (!assignedPods.remove(podId)) {
                return;
            }

            allocatedCPU -= resources.cpuMillicores();
            allocatedMemory -= resources.memoryMiB();
        }

        String report() {
            return name + " CPU " + allocatedCPU + "/" + cpuCapacity
                + "m, Memory " + allocatedMemory + "/"
                + memoryCapacity + "MiB";
        }
    }

    interface SchedulingStrategy {
        Optional<WorkerNode> select(
            List<WorkerNode> nodes,
            ResourceRequirements resources
        );
    }

    static class FirstFitScheduler implements SchedulingStrategy {
        @Override
        public Optional<WorkerNode> select(
            List<WorkerNode> nodes,
            ResourceRequirements resources
        ) {
            return nodes.stream()
                .filter(node -> node.canFit(resources))
                .findFirst();
        }
    }

    static class PodSchedulingService {
        private final List<WorkerNode> nodes;
        private final SchedulingStrategy strategy;

        PodSchedulingService(
            List<WorkerNode> nodes,
            SchedulingStrategy strategy
        ) {
            if (nodes.isEmpty()) {
                throw new IllegalArgumentException(
                    "At least one node is required"
                );
            }

            this.nodes = List.copyOf(nodes);
            this.strategy = strategy;
        }

        void schedule(PodAggregate pod) {
            ResourceRequirements resources =
                pod.spec().scheduledResources();

            WorkerNode node = strategy.select(nodes, resources)
                .orElseThrow(() ->
                    new ResourceException("No node has sufficient capacity")
                );

            node.allocate(pod.id(), resources);
            pod.assignNode(node.name());
        }

        void release(PodAggregate pod) {
            if (pod.assignedNode().isEmpty()) return;

            nodes.stream()
                .filter(n -> n.name().equals(pod.assignedNode().get()))
                .findFirst()
                .ifPresent(n -> n.release(
                    pod.id(),
                    pod.spec().scheduledResources()
                ));

            pod.record("Node resource allocation released");
        }

        List<String> nodeReports() {
            return nodes.stream()
                .map(WorkerNode::report)
                .collect(Collectors.toList());
        }
    }

    static class PodLifecycleService {

        void initialize(PodAggregate pod) {
            if (
                pod.phase() != PodPhase.PENDING ||
                pod.assignedNode().isEmpty()
            ) {
                throw new PodException(
                    "Pod must be scheduled before initialization"
                );
            }

            // Each init container completes before the next starts.
            for (ContainerRuntime runtime : pod.initContainers) {
                runtime.start();

                pod.record(
                    "Init container started: " +
                    runtime.definition().name()
                );

                runtime.terminate(0);

                pod.record(
                    "Init container completed: " +
                    runtime.definition().name()
                );
            }

            for (ContainerRuntime runtime :
                    pod.applicationRuntimes()) {
                runtime.start();

                pod.record(
                    "Application container started: " +
                    runtime.definition().name()
                );
            }

            pod.markInitialized();
            pod.setPhase(PodPhase.RUNNING);
            pod.updateReadinessCondition();
        }

        void updateReadiness(
            PodAggregate pod,
            String containerName,
            boolean ready
        ) {
            pod.container(containerName).setReadiness(ready);
            pod.updateReadinessCondition();

            pod.record(
                "Readiness updated for " + containerName +
                ": " + ready
            );
        }

        boolean terminateContainer(
            PodAggregate pod,
            String containerName,
            int exitCode,
            PodSchedulingService scheduler
        ) {
            ContainerRuntime runtime = pod.container(containerName);
            runtime.terminate(exitCode);

            pod.record(
                "Container terminated: " + containerName +
                ", exit code=" + exitCode
            );

            RestartPolicy policy = pod.spec().restartPolicy();

            boolean shouldRestart =
                policy == RestartPolicy.ALWAYS ||
                (
                    policy == RestartPolicy.ON_FAILURE &&
                    exitCode != 0
                );

            if (shouldRestart && !pod.deleting) {
                runtime.restart();

                pod.record(
                    "Container restarted: " + containerName +
                    ", restart count=" + runtime.restartCount()
                );

                pod.updateReadinessCondition();
                return true;
            }

            if (exitCode != 0 && runtime.definition().essential()) {
                pod.setPhase(PodPhase.FAILED);
                scheduler.release(pod);
                return false;
            }

            boolean allTerminated = pod.applicationRuntimes()
                .stream()
                .allMatch(c ->
                    c.state() == ContainerState.TERMINATED
                );

            if (allTerminated) {
                pod.setPhase(PodPhase.SUCCEEDED);
                scheduler.release(pod);
            }

            pod.updateReadinessCondition();
            return false;
        }

        void livenessFailure(
            PodAggregate pod,
            String containerName
        ) {
            ContainerRuntime runtime = pod.container(containerName);

            if (runtime.state() != ContainerState.RUNNING) {
                throw new PodException("Container is not running");
            }

            runtime.setLivenessHealthy(false);
            runtime.terminate(137);
            runtime.restart();
            runtime.setLivenessHealthy(true);

            pod.record(
                "Liveness probe failure caused restart: " +
                containerName
            );

            pod.updateReadinessCondition();
        }

        void shutdown(
            PodAggregate pod,
            PodSchedulingService scheduler
        ) {
            if (
                pod.phase() == PodPhase.SUCCEEDED ||
                pod.phase() == PodPhase.FAILED
            ) {
                scheduler.release(pod);
                return;
            }

            pod.deleting = true;

            pod.record(
                "Termination requested; grace period=" +
                pod.spec().terminationGracePeriodSeconds() + " seconds"
            );

            for (ContainerRuntime runtime :
                    pod.applicationRuntimes()) {
                if (runtime.state() == ContainerState.RUNNING) {
                    runtime.terminate(143);
                }
            }

            pod.updateReadinessCondition();
            pod.setPhase(PodPhase.SUCCEEDED);
            scheduler.release(pod);
            pod.record("Pod terminated");
        }
    }

    static void runProductionScenario() {
        WorkerNode nodeA = new WorkerNode(
            "worker-a", 2000, 4096
        );

        WorkerNode nodeB = new WorkerNode(
            "worker-b", 1000, 2048
        );

        PodSchedulingService scheduling =
            new PodSchedulingService(
                List.of(nodeA, nodeB),
                new FirstFitScheduler()
            );

        PodLifecycleService lifecycle =
            new PodLifecycleService();

        List<ContainerDefinition> containers = List.of(
            new ContainerDefinition(
                "api",
                "nginx:1.27",
                List.of(8080),
                new ResourceRequirements(300, 256),
                true
            ),
            new ContainerDefinition(
                "log-agent",
                "fluent-bit:3.1",
                List.of(),
                new ResourceRequirements(100, 128),
                true
            )
        );

        List<ContainerDefinition> initContainers = List.of(
            new ContainerDefinition(
                "config-check",
                "busybox:1.36",
                List.of(),
                new ResourceRequirements(50, 64),
                true
            )
        );

        PodMetadata metadata = new PodMetadata(
            "orders-api",
            "production",
            Map.of(
                "app", "orders",
                "environment", "production"
            ),
            Map.of(
                "team", "platform-engineering"
            )
        );

        PodSpec spec = new PodSpec(
            containers,
            initContainers,
            RestartPolicy.ALWAYS,
            30,
            "orders-service-account"
        );

        PodAggregate pod = new PodAggregate(metadata, spec);

        scheduling.schedule(pod);
        lifecycle.initialize(pod);

        lifecycle.updateReadiness(pod, "api", true);
        lifecycle.updateReadiness(pod, "log-agent", true);

        if (!pod.ready()) {
            throw new AssertionError("Pod should be ready");
        }

        lifecycle.updateReadiness(pod, "log-agent", false);

        if (pod.ready()) {
            throw new AssertionError(
                "Pod must not be ready when sidecar is unready"
            );
        }

        lifecycle.updateReadiness(pod, "log-agent", true);

        lifecycle.terminateContainer(
            pod,
            "api",
            1,
            scheduling
        );

        lifecycle.livenessFailure(pod, "api");

        System.out.println("\nProduction Pod state: " + pod.phase());
        System.out.println("Pod ready: " + pod.ready());

        scheduling.nodeReports().forEach(System.out::println);

        lifecycle.shutdown(pod, scheduling);

        System.out.println("\nAfter shutdown:");
        scheduling.nodeReports().forEach(System.out::println);
    }

    static void runBatchScenario() {
        PodMetadata metadata = new PodMetadata(
            "nightly-report",
            "batch",
            Map.of("job", "report"),
            Map.of()
        );

        PodSpec spec = new PodSpec(
            List.of(
                new ContainerDefinition(
                    "processor",
                    "python:3.13-slim",
                    List.of(),
                    new ResourceRequirements(200, 256),
                    true
                )
            ),
            List.of(),
            RestartPolicy.NEVER,
            20,
            "batch-service-account"
        );

        PodAggregate batch = new PodAggregate(metadata, spec);

        PodSchedulingService scheduling =
            new PodSchedulingService(
                List.of(
                    new WorkerNode("batch-node", 1000, 2048)
                ),
                new FirstFitScheduler()
            );

        PodLifecycleService lifecycle =
            new PodLifecycleService();

        scheduling.schedule(batch);
        lifecycle.initialize(batch);

        boolean restarted = lifecycle.terminateContainer(
            batch,
            "processor",
            0,
            scheduling
        );

        if (restarted || batch.phase() != PodPhase.SUCCEEDED) {
            throw new AssertionError(
                "Successful batch Pod must complete without restart"
            );
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println(
                "ENTERPRISE KUBERNETES POD MANAGEMENT\n"
            );

            runProductionScenario();

            System.out.println("\nBATCH WORKLOAD");
            runBatchScenario();

            System.out.println("\nAll enterprise lifecycle checks passed.");

        } catch (Exception exception) {
            System.err.println(
                "Pod management error: " + exception.getMessage()
            );
            System.exitCode = 1;
        }
    }
}
