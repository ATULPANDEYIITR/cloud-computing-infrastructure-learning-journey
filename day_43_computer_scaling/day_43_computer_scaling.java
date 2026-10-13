import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;

/*
 * Enterprise compute capacity planning and scaling governance.
 *
 * Requires Java 17 or later.
 *
 * Compile:
 *   javac ComputeScaling.java
 *
 * Run:
 *   java ComputeScaling
 *
 * All instance sizes, benchmarks, and prices are illustrative.
 */

public class ComputeScaling {

    enum ScalingMode {
        VERTICAL,
        HORIZONTAL
    }

    enum Resource {
        CPU,
        MEMORY,
        CONNECTIONS,
        NETWORK
    }

    record InstanceType(
        String name,
        int vcpus,
        double memoryGiB,
        int maxConnections,
        double networkGbps,
        double hourlyCost
    ) {
        InstanceType {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Instance name is required.");
            }
            if (vcpus < 1 || memoryGiB <= 0 || maxConnections < 1
                || networkGbps <= 0 || hourlyCost < 0) {
                throw new IllegalArgumentException("Invalid instance specification.");
            }
        }
    }

    record Workload(
        String name,
        double requestsPerSecond,
        double cpuCoresPerRequest,
        double memoryGiBPerReplica,
        int connectionsPerReplica,
        double networkGbpsPerReplica
    ) {
        Workload {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Workload name is required.");
            }
            if (!Double.isFinite(requestsPerSecond) || requestsPerSecond < 0
                || !Double.isFinite(cpuCoresPerRequest)
                || cpuCoresPerRequest <= 0
                || !Double.isFinite(memoryGiBPerReplica)
                || memoryGiBPerReplica <= 0
                || connectionsPerReplica < 0
                || !Double.isFinite(networkGbpsPerReplica)
                || networkGbpsPerReplica < 0) {
                throw new IllegalArgumentException("Invalid workload parameters.");
            }
        }
    }

    record CapacityPolicy(
        double cpuTarget,
        double memoryTarget,
        double connectionTarget,
        double networkTarget,
        double requestsPerCoreSecond,
        double safetyFactor
    ) {
        CapacityPolicy {
            for (double target : List.of(
                cpuTarget, memoryTarget, connectionTarget, networkTarget
            )) {
                if (!Double.isFinite(target) || target <= 0 || target > 1) {
                    throw new IllegalArgumentException(
                        "Utilization targets must be within (0, 1]."
                    );
                }
            }
            if (requestsPerCoreSecond <= 0 || safetyFactor < 1) {
                throw new IllegalArgumentException("Invalid benchmark or safety factor.");
            }
        }

        static CapacityPolicy productionPlanningDefaults() {
            return new CapacityPolicy(0.65, 0.75, 0.70, 0.70, 1.0, 1.25);
        }
    }

    record Evaluation(
        ScalingMode mode,
        InstanceType instance,
        int replicas,
        double requestedRps,
        double capacityRps,
        double hourlyCost,
        Map<Resource, Double> utilization,
        List<Resource> bottlenecks,
        List<String> violations
    ) {
        Evaluation {
            utilization = Map.copyOf(utilization);
            bottlenecks = List.copyOf(bottlenecks);
            violations = List.copyOf(violations);
        }

        boolean feasible() {
            return violations.isEmpty() && requestedRps <= capacityRps;
        }

        double estimatedMonthlyComputeCost() {
            return hourlyCost * 730;
        }
    }

    record ResourceCapacity(
        double requestsPerSecond,
        List<Resource> limitingResources
    ) {
        ResourceCapacity {
            limitingResources = List.copyOf(limitingResources);
        }
    }

    static final class CapacityPlanningService {
        private final CapacityPolicy policy;

        CapacityPlanningService(CapacityPolicy policy) {
            this.policy = policy;
        }

        ResourceCapacity capacityPerReplica(
            InstanceType instance,
            Workload workload
        ) {
            // Convert every resource constraint into a request-rate ceiling.
            Map<Resource, Double> ceilings = new TreeMap<>(
                Comparator.comparing(Enum::name)
            );

            ceilings.put(
                Resource.CPU,
                instance.vcpus() * policy.requestsPerCoreSecond()
                    * policy.cpuTarget()
                    / (workload.cpuCoresPerRequest() * policy.safetyFactor())
            );
            ceilings.put(
                Resource.MEMORY,
                instance.memoryGiB() * policy.memoryTarget()
                    / workload.memoryGiBPerReplica()
            );
            ceilings.put(
                Resource.CONNECTIONS,
                instance.maxConnections() * policy.connectionTarget()
                    / Math.max(workload.connectionsPerReplica(), 1)
            );
            ceilings.put(
                Resource.NETWORK,
                instance.networkGbps() * policy.networkTarget()
                    / Math.max(workload.networkGbpsPerReplica(), 0.001)
            );

            double minimum = ceilings.values().stream()
                .mapToDouble(Double::doubleValue)
                .min()
                .orElseThrow();

            List<Resource> bottlenecks = ceilings.entrySet().stream()
                .filter(entry -> Math.abs(entry.getValue() - minimum) < 1e-9)
                .map(Map.Entry::getKey)
                .toList();

            return new ResourceCapacity(minimum, bottlenecks);
        }

        Evaluation evaluate(
            InstanceType instance,
            int replicas,
            Workload workload,
            ScalingMode mode
        ) {
            if (replicas < 1) {
                throw new IllegalArgumentException("Replicas must be positive.");
            }

            ResourceCapacity capacity = capacityPerReplica(instance, workload);
            double totalCapacity = capacity.requestsPerSecond() * replicas;

            double cpuUtilization =
                workload.requestsPerSecond() * workload.cpuCoresPerRequest()
                    / (instance.vcpus() * replicas);
            double memoryUtilization =
                workload.memoryGiBPerReplica() / instance.memoryGiB();
            double connectionUtilization =
                (double) workload.connectionsPerReplica()
                    / instance.maxConnections();
            double networkUtilization =
                workload.networkGbpsPerReplica() / instance.networkGbps();

            Map<Resource, Double> utilization = Map.of(
                Resource.CPU, cpuUtilization,
                Resource.MEMORY, memoryUtilization,
                Resource.CONNECTIONS, connectionUtilization,
                Resource.NETWORK, networkUtilization
            );

            List<String> violations = new ArrayList<>();
            if (cpuUtilization > policy.cpuTarget()) {
                violations.add("CPU utilization target exceeded");
            }
            if (memoryUtilization > policy.memoryTarget()) {
                violations.add("Memory utilization target exceeded");
            }
            if (connectionUtilization > policy.connectionTarget()) {
                violations.add("Connection utilization target exceeded");
            }
            if (networkUtilization > policy.networkTarget()) {
                violations.add("Network utilization target exceeded");
            }
            if (workload.requestsPerSecond() > totalCapacity) {
                violations.add("Estimated throughput capacity exceeded");
            }

            return new Evaluation(
                mode,
                instance,
                replicas,
                workload.requestsPerSecond(),
                totalCapacity,
                instance.hourlyCost() * replicas,
                utilization,
                capacity.limitingResources(),
                violations
            );
        }

        Optional<Evaluation> planVertical(
            List<InstanceType> catalog,
            int fixedReplicas,
            Workload workload,
            int maximumVcpus,
            double maximumMemoryGiB
        ) {
            return catalog.stream()
                .filter(instance -> instance.vcpus() <= maximumVcpus)
                .filter(instance -> instance.memoryGiB() <= maximumMemoryGiB)
                .sorted(Comparator.comparingDouble(InstanceType::hourlyCost))
                .map(instance -> evaluate(
                    instance, fixedReplicas, workload, ScalingMode.VERTICAL
                ))
                .filter(Evaluation::feasible)
                .findFirst();
        }

        Optional<Evaluation> planHorizontal(
            InstanceType instance,
            Workload workload,
            int minimumReplicas,
            int maximumReplicas
        ) {
            if (minimumReplicas < 1 || maximumReplicas < minimumReplicas) {
                throw new IllegalArgumentException("Invalid replica bounds.");
            }

            for (int replicas = minimumReplicas;
                 replicas <= maximumReplicas;
                 replicas++) {
                Evaluation candidate = evaluate(
                    instance, replicas, workload, ScalingMode.HORIZONTAL
                );
                if (candidate.feasible()) {
                    return Optional.of(candidate);
                }
            }

            return Optional.empty();
        }
    }

    static final class AutoscalingPolicy {
        private final int minimumReplicas;
        private final int maximumReplicas;
        private final double scaleOutThreshold;
        private final double scaleInThreshold;
        private final long cooldownSeconds;

        AutoscalingPolicy(
            int minimumReplicas,
            int maximumReplicas,
            double scaleOutThreshold,
            double scaleInThreshold,
            long cooldownSeconds
        ) {
            if (minimumReplicas < 1 || maximumReplicas < minimumReplicas) {
                throw new IllegalArgumentException("Invalid replica bounds.");
            }
            if (!(0 < scaleInThreshold
                && scaleInThreshold < scaleOutThreshold
                && scaleOutThreshold <= 1)) {
                throw new IllegalArgumentException("Invalid utilization thresholds.");
            }
            if (cooldownSeconds < 0) {
                throw new IllegalArgumentException("Cooldown cannot be negative.");
            }

            this.minimumReplicas = minimumReplicas;
            this.maximumReplicas = maximumReplicas;
            this.scaleOutThreshold = scaleOutThreshold;
            this.scaleInThreshold = scaleInThreshold;
            this.cooldownSeconds = cooldownSeconds;
        }

        int minimumReplicas() {
            return minimumReplicas;
        }

        int maximumReplicas() {
            return maximumReplicas;
        }

        double scaleOutThreshold() {
            return scaleOutThreshold;
        }

        double scaleInThreshold() {
            return scaleInThreshold;
        }

        long cooldownSeconds() {
            return cooldownSeconds;
        }
    }

    static final class AutoscalingService {
        private final AutoscalingPolicy policy;
        private int replicas;
        private long lastChangeSeconds = Long.MIN_VALUE;
        private long lastObservationSeconds = Long.MIN_VALUE;

        AutoscalingService(AutoscalingPolicy policy, int initialReplicas) {
            this.policy = policy;
            if (initialReplicas < policy.minimumReplicas()
                || initialReplicas > policy.maximumReplicas()) {
                throw new IllegalArgumentException(
                    "Initial replicas must be within policy bounds."
                );
            }
            replicas = initialReplicas;
        }

        String observe(double utilization, long timestampSeconds) {
            if (!Double.isFinite(utilization) || utilization < 0
                || timestampSeconds < 0) {
                throw new IllegalArgumentException("Invalid metric observation.");
            }
            if (timestampSeconds < lastObservationSeconds) {
                throw new IllegalArgumentException(
                    "Observations must be chronological."
                );
            }
            lastObservationSeconds = timestampSeconds;

            if (lastChangeSeconds != Long.MIN_VALUE
                && timestampSeconds - lastChangeSeconds
                    < policy.cooldownSeconds()) {
                return "cooldown";
            }

            if (utilization > policy.scaleOutThreshold()) {
                if (replicas >= policy.maximumReplicas()) {
                    return "maximum-reached";
                }
                replicas++;
                lastChangeSeconds = timestampSeconds;
                return "scale-out";
            }

            if (utilization < policy.scaleInThreshold()) {
                if (replicas <= policy.minimumReplicas()) {
                    return "minimum-reached";
                }
                replicas--;
                lastChangeSeconds = timestampSeconds;
                return "scale-in";
            }

            return "stable";
        }

        int replicas() {
            return replicas;
        }
    }

    static double percentile(List<Double> values, double quantile) {
        if (values == null || values.isEmpty()
            || !Double.isFinite(quantile)
            || quantile < 0 || quantile > 1) {
            throw new IllegalArgumentException("Invalid percentile input.");
        }

        List<Double> sorted = new ArrayList<>(values);
        for (double value : sorted) {
            if (!Double.isFinite(value) || value < 0) {
                throw new IllegalArgumentException("Traffic must be non-negative.");
            }
        }
        sorted.sort(Double::compareTo);

        double position = (sorted.size() - 1) * quantile;
        int lower = (int) Math.floor(position);
        int upper = (int) Math.ceil(position);
        double fraction = position - lower;

        return sorted.get(lower)
            + (sorted.get(upper) - sorted.get(lower)) * fraction;
    }

    static void printEvaluation(String label, Optional<Evaluation> result) {
        System.out.println("\n" + label);
        if (result.isEmpty()) {
            System.out.println("No feasible configuration within the limits.");
            return;
        }

        Evaluation evaluation = result.get();
        System.out.println("Mode: " + evaluation.mode());
        System.out.println("Instance: " + evaluation.instance().name());
        System.out.println("Replicas: " + evaluation.replicas());
        System.out.printf("Demand: %.2f RPS%n", evaluation.requestedRps());
        System.out.printf("Capacity: %.2f RPS%n", evaluation.capacityRps());
        System.out.printf("Hourly cost: $%.2f%n", evaluation.hourlyCost());
        System.out.printf(
            "Monthly compute estimate: $%.2f%n",
            evaluation.estimatedMonthlyComputeCost()
        );
        System.out.println("Utilization: " + evaluation.utilization());
        System.out.println("Bottlenecks: " + evaluation.bottlenecks());
        System.out.println("Violations: " + evaluation.violations());
        System.out.println("Feasible: " + evaluation.feasible());
    }

    public static void main(String[] args) {
        List<InstanceType> catalog = List.of(
            new InstanceType("service-small", 2, 4, 500, 1, 0.08),
            new InstanceType("service-medium", 4, 8, 1500, 2, 0.16),
            new InstanceType("service-large", 8, 16, 3000, 5, 0.32),
            new InstanceType("service-xlarge", 16, 32, 6000, 10, 0.64),
            new InstanceType("service-2xlarge", 32, 64, 12000, 20, 1.28)
        );

        List<Double> hourlyTraffic = List.of(
            120.0, 145.0, 138.0, 160.0, 175.0, 210.0,
            245.0, 300.0, 360.0, 420.0, 510.0, 480.0,
            450.0, 390.0, 350.0, 320.0, 290.0, 275.0,
            260.0, 230.0, 210.0, 190.0, 160.0, 140.0
        );

        double p95 = percentile(hourlyTraffic, 0.95);
        double planningDemand = p95 * 1.30 * 1.20;

        System.out.printf("Observed P95: %.2f RPS%n", p95);
        System.out.printf("Planned demand: %.2f RPS%n", planningDemand);

        Workload workload = new Workload(
            "fulfillment-api", planningDemand, 0.08, 2.0, 300, 0.15
        );

        CapacityPlanningService planner = new CapacityPlanningService(
            CapacityPolicy.productionPlanningDefaults()
        );

        printEvaluation(
            "Vertical scaling",
            planner.planVertical(catalog, 2, workload, 64, 128)
        );

        printEvaluation(
            "Horizontal scaling",
            planner.planHorizontal(catalog.get(1), workload, 2, 20)
        );

        System.out.println("\nAutoscaling state transitions");
        AutoscalingPolicy policy = new AutoscalingPolicy(2, 8, 0.70, 0.30, 60);
        AutoscalingService autoscaler = new AutoscalingService(policy, 3);

        for (long[] observation : new long[][]{
            {0, 82},
            {20, 90},
            {65, 91},
            {130, 15},
            {200, 12}
        }) {
            String action = autoscaler.observe(
                observation[1] / 100.0, observation[0]
            );
            System.out.printf(
                "t=%ds utilization=%d%% action=%s replicas=%d%n",
                observation[0], observation[1], action, autoscaler.replicas()
            );
        }

        // These checks cover infeasible workloads and planning boundaries.
        Workload small = new Workload("small-api", 1, 0.01, 0.5, 10, 0.01);
        if (planner.planVertical(catalog, 1, small, 64, 128).isEmpty()) {
            throw new IllegalStateException("Expected a feasible small workload.");
        }

        Workload impossible = new Workload(
            "oversized-api", 1_000_000, 1.0, 1000, 1_000_000, 1000
        );
        if (planner.planVertical(catalog, 1, impossible, 64, 128).isPresent()) {
            throw new IllegalStateException("Impossible vertical plan was accepted.");
        }
        if (planner.planHorizontal(catalog.get(0), impossible, 2, 3).isPresent()) {
            throw new IllegalStateException("Impossible horizontal plan was accepted.");
        }

        AutoscalingService minimumTest = new AutoscalingService(policy, 2);
        if (!minimumTest.observe(0.10, 0).equals("minimum-reached")) {
            throw new IllegalStateException("Minimum replica guard failed.");
        }

        System.out.println("\nAll enterprise planning assertions passed.");
    }
}
