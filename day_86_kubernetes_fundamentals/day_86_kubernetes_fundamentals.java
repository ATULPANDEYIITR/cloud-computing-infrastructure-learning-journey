import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Predicate;
import java.util.stream.Collectors;

/**
 * Kubernetes Fundamentals: Enterprise Cluster Management
 *
 * Models:
 * - Control plane and worker nodes
 * - Declarative workloads
 * - Scheduling and resource allocation
 * - Deployment reconciliation
 * - Replica management
 * - Container health and readiness
 * - Service discovery
 * - Rolling update strategies
 * - Admission policies
 * - Node draining and failure recovery
 *
 * Java 17, standard library only.
 */
public class KubernetesEnterprise {

    enum PodPhase {
        PENDING,
        RUNNING,
        FAILED,
        TERMINATING
    }

    enum NodeCondition {
        READY,
        NOT_READY,
        DRAINING
    }

    enum WorkloadCondition {
        HEALTHY,
        DEGRADED,
        UNAVAILABLE
    }

    enum EventType {
        NODE_ADDED,
        DEPLOYMENT_CREATED,
        POD_SCHEDULED,
        POD_FAILED,
        POD_REPLACED,
        DEPLOYMENT_SCALED,
        UPDATE_COMPLETED,
        UPDATE_FAILED,
        NODE_DRAINED,
        ADMISSION_REJECTED
    }

    record ResourceRequest(
        int cpuMillicores,
        int memoryMB
    ) {
        ResourceRequest {
            if (cpuMillicores <= 0 || memoryMB <= 0) {
                throw new IllegalArgumentException(
                    "Resource requests must be positive."
                );
            }
        }
    }

    record ClusterEvent(
        long sequence,
        Instant timestamp,
        EventType type,
        String message
    ) {}

    record ServiceEndpoint(
        String podName,
        String nodeName,
        int targetPort
    ) {}

    record WorkloadSpec(
        String name,
        String image,
        int replicas,
        Map<String, String> selector,
        ResourceRequest resources
    ) {
        WorkloadSpec {
            validateName(name);

            Objects.requireNonNull(image);
            Objects.requireNonNull(selector);
            Objects.requireNonNull(resources);

            if (image.isBlank() || !image.contains(":")) {
                throw new IllegalArgumentException(
                    "Image must contain an explicit tag."
                );
            }

            if (replicas < 0) {
                throw new IllegalArgumentException(
                    "Replicas cannot be negative."
                );
            }

            if (selector.isEmpty()) {
                throw new IllegalArgumentException(
                    "Selector cannot be empty."
                );
            }

            selector = Map.copyOf(selector);
        }
    }

    static void validateName(String name) {
        if (
            name == null ||
            !name.matches(
                "[a-z0-9]([-a-z0-9]*[a-z0-9])?"
            ) ||
            name.length() > 63
        ) {
            throw new IllegalArgumentException(
                "Invalid Kubernetes resource name."
            );
        }
    }

    static class KubernetesException extends RuntimeException {
        KubernetesException(String message) {
            super(message);
        }
    }

    static class Node {
        private final String name;
        private final int cpuCapacity;
        private final int memoryCapacity;

        private NodeCondition condition = NodeCondition.READY;

        private final Map<String, Pod> pods =
            new LinkedHashMap<>();

        Node(String name, int cpuCapacity, int memoryCapacity) {
            validateName(name);

            if (cpuCapacity <= 0 || memoryCapacity <= 0) {
                throw new IllegalArgumentException(
                    "Invalid node capacity."
                );
            }

            this.name = name;
            this.cpuCapacity = cpuCapacity;
            this.memoryCapacity = memoryCapacity;
        }

        int allocatedCPU() {
            return pods.values().stream()
                .filter(Pod::consumesResources)
                .mapToInt(p -> p.resources.cpuMillicores())
                .sum();
        }

        int allocatedMemory() {
            return pods.values().stream()
                .filter(Pod::consumesResources)
                .mapToInt(p -> p.resources.memoryMB())
                .sum();
        }

        boolean canSchedule(Pod pod) {
            return condition == NodeCondition.READY &&
                allocatedCPU() + pod.resources.cpuMillicores()
                    <= cpuCapacity &&
                allocatedMemory() + pod.resources.memoryMB()
                    <= memoryCapacity;
        }

        double cpuUtilization() {
            return (double) allocatedCPU() / cpuCapacity;
        }

        void addPod(Pod pod) {
            if (!canSchedule(pod)) {
                throw new KubernetesException(
                    "Node cannot accommodate pod."
                );
            }

            pods.put(pod.id, pod);
        }

        void removePod(String id) {
            pods.remove(id);
        }

        void setCondition(NodeCondition condition) {
            this.condition = condition;
        }

        List<Pod> pods() {
            return List.copyOf(pods.values());
        }
    }

    static class Pod {
        private final String id = UUID.randomUUID().toString();
        private final String name;
        private final String deploymentName;
        private final Map<String, String> labels;
        private final ResourceRequest resources;

        private String image;
        private String nodeName;
        private PodPhase phase = PodPhase.PENDING;
        private boolean ready;
        private int restartCount;
        private final int revision;

        Pod(
            String name,
            String deploymentName,
            String image,
            Map<String, String> labels,
            ResourceRequest resources,
            int revision
        ) {
            this.name = name;
            this.deploymentName = deploymentName;
            this.image = image;
            this.labels = Map.copyOf(labels);
            this.resources = resources;
            this.revision = revision;
        }

        boolean consumesResources() {
            return phase == PodPhase.RUNNING ||
                phase == PodPhase.PENDING;
        }

        void markRunning(String nodeName) {
            this.nodeName = nodeName;
            this.phase = PodPhase.RUNNING;
            this.ready = true;
        }

        void fail() {
            phase = PodPhase.FAILED;
            ready = false;
            nodeName = null;
            restartCount++;
        }
    }

    static class Deployment {
        private final WorkloadSpec spec;

        private int desiredReplicas;
        private int generation = 1;
        private int revision = 1;
        private String image;

        private final Map<String, Pod> pods =
            new LinkedHashMap<>();

        Deployment(WorkloadSpec spec) {
            this.spec = spec;
            this.desiredReplicas = spec.replicas();
            this.image = spec.image();
        }

        int runningReplicas() {
            return (int) pods.values().stream()
                .filter(p -> p.phase == PodPhase.RUNNING)
                .count();
        }

        WorkloadCondition condition() {
            int ready = (int) pods.values().stream()
                .filter(p ->
                    p.phase == PodPhase.RUNNING && p.ready
                )
                .count();

            if (ready == desiredReplicas) {
                return WorkloadCondition.HEALTHY;
            }

            if (ready == 0 && desiredReplicas > 0) {
                return WorkloadCondition.UNAVAILABLE;
            }

            return WorkloadCondition.DEGRADED;
        }
    }

    static class AdmissionPolicy {
        private final List<Predicate<Pod>> rules =
            new ArrayList<>();

        void addRule(Predicate<Pod> rule) {
            rules.add(Objects.requireNonNull(rule));
        }

        void validate(Pod pod) {
            for (Predicate<Pod> rule : rules) {
                if (!rule.test(pod)) {
                    throw new KubernetesException(
                        "Pod rejected by admission policy: " +
                        pod.name
                    );
                }
            }
        }
    }

    static class Cluster {
        private final String name;

        private final List<Node> nodes =
            new ArrayList<>();

        private final Map<String, Deployment> deployments =
            new LinkedHashMap<>();

        private final Map<String, Service> services =
            new LinkedHashMap<>();

        private final List<ClusterEvent> events =
            new CopyOnWriteArrayList<>();

        private final AdmissionPolicy admission;

        private long sequence;
        private long podSequence;

        Cluster(String name, AdmissionPolicy admission) {
            validateName(name);
            this.name = name;
            this.admission = admission;
        }

        private void log(EventType type, String message) {
            events.add(new ClusterEvent(
                ++sequence,
                Instant.now(),
                type,
                message
            ));
        }

        void addNode(Node node) {
            if (nodes.stream().anyMatch(
                n -> n.name.equals(node.name)
            )) {
                throw new KubernetesException(
                    "Duplicate node name."
                );
            }

            nodes.add(node);

            log(EventType.NODE_ADDED, node.name);
        }

        void createDeployment(WorkloadSpec spec) {
            if (deployments.containsKey(spec.name())) {
                throw new KubernetesException(
                    "Deployment already exists."
                );
            }

            deployments.put(
                spec.name(),
                new Deployment(spec)
            );

            log(
                EventType.DEPLOYMENT_CREATED,
                spec.name()
            );
        }

        void createService(Service service) {
            if (services.containsKey(service.name)) {
                throw new KubernetesException(
                    "Service already exists."
                );
            }

            services.put(service.name, service);
        }

        private Pod newPod(Deployment deployment) {
            long id = ++podSequence;

            return new Pod(
                deployment.spec.name() + "-" + id,
                deployment.spec.name(),
                deployment.image,
                deployment.spec.selector(),
                deployment.spec.resources(),
                deployment.revision
            );
        }

        private Node chooseNode(Pod pod) {
            return nodes.stream()
                .filter(node -> node.canSchedule(pod))
                .min(
                    Comparator
                        .comparingDouble(Node::cpuUtilization)
                        .thenComparing(node -> node.name)
                )
                .orElseThrow(() ->
                    new KubernetesException(
                        "No feasible worker node for " + pod.name
                    )
                );
        }

        private void schedule(Pod pod) {
            try {
                admission.validate(pod);
            } catch (KubernetesException exception) {
                log(
                    EventType.ADMISSION_REJECTED,
                    exception.getMessage()
                );

                throw exception;
            }

            Node node = chooseNode(pod);

            node.addPod(pod);
            pod.markRunning(node.name);

            log(
                EventType.POD_SCHEDULED,
                pod.name + " -> " + node.name
            );
        }

        void reconcile(String deploymentName) {
            Deployment deployment = deployments.get(
                deploymentName
            );

            if (deployment == null) {
                throw new KubernetesException(
                    "Deployment does not exist."
                );
            }

            int active = deployment.runningReplicas();

            while (active < deployment.desiredReplicas) {
                Pod pod = newPod(deployment);

                try {
                    schedule(pod);
                    deployment.pods.put(pod.id, pod);
                    active++;
                } catch (KubernetesException exception) {
                    System.err.println(
                        "Reconciliation blocked: " +
                        exception.getMessage()
                    );
                    break;
                }
            }

            if (active > deployment.desiredReplicas) {
                List<Pod> running = deployment.pods.values()
                    .stream()
                    .filter(p -> p.phase == PodPhase.RUNNING)
                    .toList();

                for (int i = 0;
                     i < active - deployment.desiredReplicas;
                     i++) {

                    deletePod(deployment, running.get(i));
                }
            }
        }

        private void deletePod(
            Deployment deployment,
            Pod pod
        ) {
            Node node = nodes.stream()
                .filter(n -> n.name.equals(pod.nodeName))
                .findFirst()
                .orElse(null);

            if (node != null) {
                node.removePod(pod.id);
            }

            pod.phase = PodPhase.TERMINATING;
            pod.ready = false;

            deployment.pods.remove(pod.id);
        }

        void scale(String deploymentName, int replicas) {
            if (replicas < 0) {
                throw new IllegalArgumentException(
                    "Replicas cannot be negative."
                );
            }

            Deployment deployment = deployments.get(
                deploymentName
            );

            if (deployment == null) {
                throw new KubernetesException(
                    "Deployment not found."
                );
            }

            deployment.desiredReplicas = replicas;
            deployment.generation++;

            log(
                EventType.DEPLOYMENT_SCALED,
                deploymentName + " replicas=" + replicas
            );

            reconcile(deploymentName);
        }

        void failPod(String deploymentName, String podId) {
            Deployment deployment = deployments.get(
                deploymentName
            );

            if (deployment == null) {
                throw new KubernetesException(
                    "Deployment not found."
                );
            }

            Pod pod = deployment.pods.get(podId);

            if (pod == null) {
                throw new KubernetesException(
                    "Pod not found."
                );
            }

            Node node = nodes.stream()
                .filter(n -> n.name.equals(pod.nodeName))
                .findFirst()
                .orElse(null);

            if (node != null) {
                node.removePod(pod.id);
            }

            pod.fail();

            log(EventType.POD_FAILED, pod.name);

            reconcile(deploymentName);
        }

        boolean rollingUpdate(
            String deploymentName,
            String newImage
        ) {
            Deployment deployment = deployments.get(
                deploymentName
            );

            if (deployment == null || newImage == null ||
                !newImage.contains(":")) {
                throw new IllegalArgumentException(
                    "Invalid rolling update."
                );
            }

            String previousImage = deployment.image;
            int previousRevision = deployment.revision;

            deployment.image = newImage;
            deployment.revision++;
            deployment.generation++;

            List<Pod> oldPods = deployment.pods.values()
                .stream()
                .filter(p -> p.phase == PodPhase.RUNNING)
                .toList();

            List<Pod> replacements = new ArrayList<>();

            try {
                for (Pod oldPod : oldPods) {
                    Pod replacement = newPod(deployment);

                    schedule(replacement);
                    deployment.pods.put(
                        replacement.id,
                        replacement
                    );

                    replacements.add(replacement);

                    deletePod(deployment, oldPod);
                }

                log(
                    EventType.UPDATE_COMPLETED,
                    deploymentName
                );

                return true;

            } catch (KubernetesException exception) {
                for (Pod replacement : replacements) {
                    deletePod(deployment, replacement);
                }

                deployment.image = previousImage;
                deployment.revision = previousRevision;
                deployment.generation--;

                log(
                    EventType.UPDATE_FAILED,
                    exception.getMessage()
                );

                reconcile(deploymentName);
                return false;
            }
        }

        void drainNode(String nodeName) {
            Node node = nodes.stream()
                .filter(n -> n.name.equals(nodeName))
                .findFirst()
                .orElseThrow(() ->
                    new KubernetesException("Node not found.")
                );

            node.setCondition(NodeCondition.DRAINING);

            for (Pod pod : node.pods()) {
                Deployment deployment = deployments.get(
                    pod.deploymentName
                );

                if (deployment != null) {
                    pod.fail();
                    node.removePod(pod.id);
                    reconcile(deployment.spec.name());
                }
            }

            log(EventType.NODE_DRAINED, nodeName);
        }

        List<ServiceEndpoint> endpoints(String serviceName) {
            Service service = services.get(serviceName);

            if (service == null) {
                throw new KubernetesException(
                    "Service not found."
                );
            }

            return nodes.stream()
                .flatMap(node -> node.pods().stream()
                    .filter(pod ->
                        pod.phase == PodPhase.RUNNING &&
                        pod.ready &&
                        service.matches(pod)
                    )
                    .map(pod -> new ServiceEndpoint(
                        pod.name,
                        node.name,
                        service.targetPort
                    ))
                )
                .toList();
        }

        void report() {
            System.out.println("\nCLUSTER: " + name);

            for (Node node : nodes) {
                System.out.printf(
                    "%s | CPU %d/%d | Memory %d/%d MB | Pods %d | %s%n",
                    node.name,
                    node.allocatedCPU(),
                    node.cpuCapacity,
                    node.allocatedMemory(),
                    node.memoryCapacity,
                    node.pods.size(),
                    node.condition
                );
            }

            System.out.println("\nDEPLOYMENTS");

            deployments.values().forEach(deployment ->
                System.out.printf(
                    "%s | desired=%d | running=%d | image=%s | state=%s%n",
                    deployment.spec.name(),
                    deployment.desiredReplicas,
                    deployment.runningReplicas(),
                    deployment.image,
                    deployment.condition()
                )
            );
        }

        List<ClusterEvent> events() {
            return List.copyOf(events);
        }
    }

    static class Service {
        private final String name;
        private final Map<String, String> selector;
        private final int port;
        private final int targetPort;

        Service(
            String name,
            Map<String, String> selector,
            int port,
            int targetPort
        ) {
            validateName(name);

            if (
                selector.isEmpty() ||
                port < 1 || port > 65535 ||
                targetPort < 1 || targetPort > 65535
            ) {
                throw new IllegalArgumentException(
                    "Invalid Service configuration."
                );
            }

            this.name = name;
            this.selector = Map.copyOf(selector);
            this.port = port;
            this.targetPort = targetPort;
        }

        boolean matches(Pod pod) {
            return selector.entrySet().stream()
                .allMatch(entry ->
                    Objects.equals(
                        pod.labels.get(entry.getKey()),
                        entry.getValue()
                    )
                );
        }
    }

    public static void main(String[] args) {
        AdmissionPolicy policy = new AdmissionPolicy();

        policy.addRule(pod ->
            pod.image.startsWith("registry.example.com/")
        );

        policy.addRule(pod ->
            pod.resources.memoryMB() >= 128
        );

        Cluster cluster = new Cluster(
            "production-cluster",
            policy
        );

        cluster.addNode(
            new Node("worker-01", 4000, 8192)
        );

        cluster.addNode(
            new Node("worker-02", 4000, 8192)
        );

        cluster.addNode(
            new Node("worker-03", 2000, 4096)
        );

        WorkloadSpec paymentSpec = new WorkloadSpec(
            "payment-api",
            "registry.example.com/payment:v1",
            3,
            Map.of("app", "payment-api"),
            new ResourceRequest(500, 512)
        );

        cluster.createDeployment(paymentSpec);

        cluster.createService(
            new Service(
                "payment-service",
                Map.of("app", "payment-api"),
                80,
                8080
            )
        );

        System.out.println("\nINITIAL RECONCILIATION");

        cluster.reconcile("payment-api");
        cluster.report();

        System.out.println("\nSERVICE ENDPOINTS");

        cluster.endpoints("payment-service")
            .forEach(System.out::println);

        System.out.println("\nSCALING");

        cluster.scale("payment-api", 5);

        System.out.println("\nROLLING UPDATE");

        boolean success = cluster.rollingUpdate(
            "payment-api",
            "registry.example.com/payment:v2"
        );

        System.out.println("Update successful: " + success);

        System.out.println("\nNODE DRAINING");

        cluster.drainNode("worker-03");

        cluster.report();

        System.out.println("\nFINAL EVENTS");

        cluster.events().forEach(System.out::println);
    }
}
