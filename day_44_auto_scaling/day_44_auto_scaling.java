import java.time.Duration;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

/*
 * Enterprise auto scaling model for a customer-facing order processing service.
 *
 * Java 17 or later:
 *   javac AutoScalingEnterprise.java
 *   java AutoScalingEnterprise
 *
 * This is a deterministic simulation, not a cloud-provider SDK client.
 */

public class AutoScalingEnterprise {

    enum InstanceStatus {
        WARMING,
        HEALTHY,
        UNHEALTHY,
        TERMINATING
    }

    enum MetricName {
        CPU_UTILIZATION,
        REQUESTS_PER_SECOND,
        P95_LATENCY_MS,
        ERROR_RATE_PERCENT
    }

    enum PolicyKind {
        TARGET_TRACKING,
        STEP_SCALING,
        SCHEDULED
    }

    enum ScalingDirection {
        OUT,
        IN
    }

    record MetricSample(
        Instant timestamp,
        double cpuPercent,
        double requestsPerSecond,
        double p95LatencyMs,
        double errorRatePercent
    ) {
        MetricSample {
            Objects.requireNonNull(timestamp, "timestamp");
            requireRange(cpuPercent, 0, 100, "CPU");
            requireRange(requestsPerSecond, 0, Double.MAX_VALUE, "request rate");
            requireRange(p95LatencyMs, 0, Double.MAX_VALUE, "p95 latency");
            requireRange(errorRatePercent, 0, 100, "error rate");
        }

        double valueFor(MetricName name) {
            return switch (name) {
                case CPU_UTILIZATION -> cpuPercent;
                case REQUESTS_PER_SECOND -> requestsPerSecond;
                case P95_LATENCY_MS -> p95LatencyMs;
                case ERROR_RATE_PERCENT -> errorRatePercent;
            };
        }
    }

    static void requireRange(
        double value,
        double minimum,
        double maximum,
        String label
    ) {
        if (!Double.isFinite(value) || value < minimum || value > maximum) {
            throw new IllegalArgumentException(
                label + " must be between " + minimum + " and " + maximum
            );
        }
    }

    record ScalingPolicy(
        String name,
        PolicyKind kind,
        MetricName metric,
        double target,
        double scaleOutRatio,
        double scaleInRatio,
        int scaleOutStep,
        int scaleInStep,
        Duration scaleOutCooldown,
        Duration scaleInCooldown,
        int evaluationPeriods,
        int metricWindowSize
    ) {
        ScalingPolicy {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Policy name is required.");
            }
            Objects.requireNonNull(kind);
            Objects.requireNonNull(metric);
            Objects.requireNonNull(scaleOutCooldown);
            Objects.requireNonNull(scaleInCooldown);

            requireRange(target, Double.MIN_VALUE, Double.MAX_VALUE, "target");

            if (
                scaleOutRatio <= 1 ||
                scaleInRatio <= 0 ||
                scaleInRatio >= 1 ||
                scaleOutStep < 1 ||
                scaleInStep < 1 ||
                evaluationPeriods < 1 ||
                metricWindowSize < 1 ||
                scaleOutCooldown.isNegative() ||
                scaleInCooldown.isNegative()
            ) {
                throw new IllegalArgumentException("Invalid scaling policy.");
            }
        }
    }

    record ScalingEvent(
        Instant timestamp,
        String type,
        String details,
        int oldDesired,
        int newDesired
    ) {}

    static final class ComputeInstance {
        private final String id;
        private final Instant launchedAt;
        private Instant readyAt;
        private InstanceStatus status;
        private boolean protectedFromScaleIn;

        ComputeInstance(Instant now, Duration warmup) {
            id = "order-node-" + UUID.randomUUID().toString().substring(0, 8);
            launchedAt = now;
            readyAt = now.plus(warmup);
            status = warmup.isZero()
                ? InstanceStatus.HEALTHY
                : InstanceStatus.WARMING;
        }

        String id() {
            return id;
        }

        Instant launchedAt() {
            return launchedAt;
        }

        InstanceStatus status() {
            return status;
        }

        boolean protectedFromScaleIn() {
            return protectedFromScaleIn;
        }

        void protectFromScaleIn(boolean value) {
            protectedFromScaleIn = value;
        }

        void updateReadiness(Instant now) {
            if (status == InstanceStatus.WARMING && !now.isBefore(readyAt)) {
                status = InstanceStatus.HEALTHY;
            }
        }

        void markUnhealthy() {
            status = InstanceStatus.UNHEALTHY;
        }

        void terminate() {
            status = InstanceStatus.TERMINATING;
        }
    }

    static final class ScalingGroup {
        private final String name;
        private final int minimum;
        private final int maximum;
        private final Duration instanceWarmup;
        private final Map<String, ComputeInstance> instances = new HashMap<>();
        private final List<ScalingEvent> events = new ArrayList<>();

        private int desired;
        private Instant lastScaleOut;
        private Instant lastScaleIn;

        ScalingGroup(
            String name,
            int minimum,
            int maximum,
            int desired,
            Duration instanceWarmup
        ) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Group name is required.");
            }
            if (
                minimum < 0 ||
                maximum < minimum ||
                desired < minimum ||
                desired > maximum ||
                instanceWarmup == null ||
                instanceWarmup.isNegative()
            ) {
                throw new IllegalArgumentException("Invalid group configuration.");
            }

            this.name = name;
            this.minimum = minimum;
            this.maximum = maximum;
            this.desired = desired;
            this.instanceWarmup = instanceWarmup;
        }

        synchronized int desired() {
            return desired;
        }

        synchronized int actual() {
            return instances.size();
        }

        synchronized int healthy() {
            return (int) instances.values().stream()
                .filter(instance -> instance.status() == InstanceStatus.HEALTHY)
                .count();
        }

        synchronized List<String> instanceIds() {
            return List.copyOf(instances.keySet());
        }

        synchronized Map<InstanceStatus, Long> statusCounts() {
            Map<InstanceStatus, Long> counts =
                new EnumMap<>(InstanceStatus.class);

            for (InstanceStatus status : InstanceStatus.values()) {
                counts.put(status, 0L);
            }

            for (ComputeInstance instance : instances.values()) {
                counts.merge(instance.status(), 1L, Long::sum);
            }

            return Map.copyOf(counts);
        }

        synchronized void reconcile(Instant now) {
            for (ComputeInstance instance : instances.values()) {
                instance.updateReadiness(now);
            }

            while (instances.size() < desired) {
                ComputeInstance instance =
                    new ComputeInstance(now, instanceWarmup);
                instances.put(instance.id(), instance);
                events.add(new ScalingEvent(
                    now, "instance_launched", instance.id(), desired, desired
                ));
            }

            while (instances.size() > desired) {
                Optional<ComputeInstance> candidate = instances.values().stream()
                    .filter(instance -> !instance.protectedFromScaleIn())
                    .min(Comparator.comparing(ComputeInstance::launchedAt));

                if (candidate.isEmpty()) {
                    events.add(new ScalingEvent(
                        now,
                        "scale_in_blocked",
                        "All remaining instances are protected.",
                        desired,
                        desired
                    ));
                    break;
                }

                ComputeInstance instance = candidate.get();
                instance.terminate();
                instances.remove(instance.id());
                events.add(new ScalingEvent(
                    now, "instance_terminated", instance.id(), desired, desired
                ));
            }
        }

        synchronized boolean changeCapacity(
            int delta,
            Instant now,
            String reason
        ) {
            int oldDesired = desired;
            int next = Math.max(minimum, Math.min(maximum, desired + delta));

            if (next == oldDesired) {
                events.add(new ScalingEvent(
                    now, "capacity_unchanged", reason, oldDesired, oldDesired
                ));
                return false;
            }

            desired = next;
            String action = next > oldDesired ? "scale_out" : "scale_in";

            if (next > oldDesired) {
                lastScaleOut = now;
            } else {
                lastScaleIn = now;
            }

            events.add(new ScalingEvent(
                now, action, reason, oldDesired, next
            ));
            reconcile(now);
            return true;
        }

        synchronized boolean cooldownActive(
            ScalingDirection direction,
            Instant now,
            Duration duration
        ) {
            Instant last = direction == ScalingDirection.OUT
                ? lastScaleOut
                : lastScaleIn;

            return last != null &&
                Duration.between(last, now).compareTo(duration) < 0;
        }

        synchronized void protectInstance(String instanceId, boolean protect) {
            ComputeInstance instance = instances.get(instanceId);
            if (instance == null) {
                throw new IllegalArgumentException(
                    "Unknown instance: " + instanceId
                );
            }
            instance.protectFromScaleIn(protect);
        }

        synchronized void markUnhealthy(String instanceId, Instant now) {
            ComputeInstance instance = instances.get(instanceId);
            if (instance == null) {
                throw new IllegalArgumentException(
                    "Unknown instance: " + instanceId
                );
            }

            instance.markUnhealthy();
            instances.remove(instanceId);
            events.add(new ScalingEvent(
                now, "health_failure", instanceId, desired, desired
            ));

            // Replace the failed instance without changing desired capacity.
            reconcile(now);
        }

        synchronized List<ScalingEvent> events() {
            return List.copyOf(events);
        }
    }

    static final class MetricWindow {
        private final int maximumSize;
        private final Deque<MetricSample> samples = new ArrayDeque<>();
        private Instant lastTimestamp;

        MetricWindow(int maximumSize) {
            if (maximumSize < 1) {
                throw new IllegalArgumentException("Window size must be positive.");
            }
            this.maximumSize = maximumSize;
        }

        void add(MetricSample sample) {
            if (
                lastTimestamp != null &&
                sample.timestamp().isBefore(lastTimestamp)
            ) {
                throw new IllegalArgumentException(
                    "Metrics must arrive in chronological order."
                );
            }

            samples.addLast(sample);
            lastTimestamp = sample.timestamp();

            while (samples.size() > maximumSize) {
                samples.removeFirst();
            }
        }

        OptionalDouble average(MetricName metric) {
            if (samples.isEmpty()) {
                return OptionalDouble.empty();
            }

            return OptionalDouble.of(
                samples.stream()
                    .mapToDouble(sample -> sample.valueFor(metric))
                    .average()
                    .orElseThrow()
            );
        }

        int size() {
            return samples.size();
        }
    }

    static final class ScalingService {
        private final ScalingGroup group;
        private final ScalingPolicy policy;
        private final MetricWindow window;

        private int scaleOutBreaches;
        private int scaleInBreaches;

        ScalingService(ScalingGroup group, ScalingPolicy policy) {
            this.group = Objects.requireNonNull(group);
            this.policy = Objects.requireNonNull(policy);

            if (policy.kind() == PolicyKind.SCHEDULED) {
                throw new IllegalArgumentException(
                    "Scheduled policies are evaluated by the scheduler."
                );
            }

            window = new MetricWindow(policy.metricWindowSize());
        }

        synchronized String evaluate(MetricSample sample) {
            group.reconcile(sample.timestamp());
            window.add(sample);

            if (group.healthy() == 0) {
                return "waiting_for_healthy_capacity";
            }

            OptionalDouble optionalAverage = window.average(policy.metric());
            if (optionalAverage.isEmpty()) {
                return "waiting_for_metrics";
            }

            double average = optionalAverage.getAsDouble();
            double ratio = average / policy.target();

            if (ratio >= policy.scaleOutRatio()) {
                scaleOutBreaches++;
                scaleInBreaches = 0;
            } else if (ratio <= policy.scaleInRatio()) {
                scaleInBreaches++;
                scaleOutBreaches = 0;
            } else {
                scaleOutBreaches = 0;
                scaleInBreaches = 0;
                return "hold";
            }

            if (scaleOutBreaches >= policy.evaluationPeriods()) {
                if (group.cooldownActive(
                    ScalingDirection.OUT,
                    sample.timestamp(),
                    policy.scaleOutCooldown()
                )) {
                    return "scale_out_cooldown";
                }

                int delta = Math.max(
                    1,
                    Math.min(
                        4,
                        (int) Math.ceil(group.desired() * (ratio - 1))
                    )
                );
                scaleOutBreaches = 0;
                group.changeCapacity(
                    delta,
                    sample.timestamp(),
                    policy.name() + ": average=" + average
                );
                return "scale_out:" + delta;
            }

            if (scaleInBreaches >= policy.evaluationPeriods()) {
                if (group.cooldownActive(
                    ScalingDirection.IN,
                    sample.timestamp(),
                    policy.scaleInCooldown()
                )) {
                    return "scale_in_cooldown";
                }

                scaleInBreaches = 0;
                boolean changed = group.changeCapacity(
                    -policy.scaleInStep(),
                    sample.timestamp(),
                    policy.name() + ": sustained low utilization"
                );
                return changed ? "scale_in" : "minimum_capacity";
            }

            return "awaiting_confirmation";
        }
    }

    record ScheduledAction(
        String name,
        Instant executionTime,
        int desiredCapacity
    ) {
        ScheduledAction {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Action name is required.");
            }
            Objects.requireNonNull(executionTime);
            if (desiredCapacity < 0) {
                throw new IllegalArgumentException("Capacity cannot be negative.");
            }
        }
    }

    static void applyScheduledAction(
        ScalingGroup group,
        ScheduledAction action,
        Instant now
    ) {
        if (now.isBefore(action.executionTime())) {
            System.out.println("Scheduled action is not due: " + action.name());
            return;
        }

        int delta = action.desiredCapacity() - group.desired();
        group.changeCapacity(delta, now, "scheduled: " + action.name());
    }

    static double estimateMonthlyCost(int instanceHours, double hourlyRate) {
        if (instanceHours < 0 || !Double.isFinite(hourlyRate) || hourlyRate < 0) {
            throw new IllegalArgumentException("Invalid cost input.");
        }
        return instanceHours * hourlyRate;
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-10-14T08:00:00Z");

        ScalingGroup group = new ScalingGroup(
            "order-processing",
            2,
            12,
            3,
            Duration.ofSeconds(60)
        );

        ScalingPolicy policy = new ScalingPolicy(
            "order-cpu-target",
            PolicyKind.TARGET_TRACKING,
            MetricName.CPU_UTILIZATION,
            55.0,
            1.10,
            0.75,
            2,
            1,
            Duration.ofSeconds(120),
            Duration.ofSeconds(180),
            2,
            2
        );

        ScalingService service = new ScalingService(group, policy);
        group.reconcile(start);

        double[][] workload = {
            {35, 120, 110, 0.1},
            {62, 210, 190, 0.2},
            {75, 290, 300, 0.4},
            {83, 370, 390, 1.2},
            {79, 360, 410, 1.4},
            {48, 230, 220, 0.3},
            {34, 145, 145, 0.1},
            {29, 115, 120, 0.1},
            {25, 90, 100, 0.1}
        };

        System.out.println("ENTERPRISE AUTO SCALING SERVICE");
        System.out.println("==============================");

        for (int i = 0; i < workload.length; i++) {
            Instant timestamp = start.plusSeconds(i * 60L);
            double[] row = workload[i];

            MetricSample sample = new MetricSample(
                timestamp, row[0], row[1], row[2], row[3]
            );

            String decision = service.evaluate(sample);

            System.out.printf(
                "%s CPU=%5.1f%% latency=%5.0fms decision=%-32s desired=%2d "
                    + "actual=%2d healthy=%2d%n",
                timestamp,
                sample.cpuPercent(),
                sample.p95LatencyMs(),
                decision,
                group.desired(),
                group.actual(),
                group.healthy()
            );
        }

        System.out.println("\nScheduled business-hours adjustment");
        applyScheduledAction(
            group,
            new ScheduledAction(
                "morning traffic preparation",
                start.plus(Duration.ofHours(1)),
                5
            ),
            start.plus(Duration.ofHours(1))
        );

        System.out.println("\nHealth replacement");
        List<String> ids = group.instanceIds();
        if (!ids.isEmpty()) {
            group.markUnhealthy(
                ids.get(0),
                start.plus(Duration.ofHours(1)).plusSeconds(30)
            );
        }

        System.out.println("Instance states: " + group.statusCounts());
        System.out.println("Desired capacity: " + group.desired());
        System.out.println("Actual capacity: " + group.actual());

        double cost = estimateMonthlyCost(
            group.actual() * 24 * 30,
            0.048
        );
        System.out.printf("Illustrative monthly compute cost: $%.2f%n", cost);

        System.out.println("\nGovernance event history");
        for (ScalingEvent event : group.events()) {
            System.out.printf(
                "%s | %-22s | %2d -> %2d | %s%n",
                event.timestamp(),
                event.type(),
                event.oldDesired(),
                event.newDesired(),
                event.details()
            );
        }

        try {
            new MetricSample(start, 105, 100, 200, 0.1);
        } catch (IllegalArgumentException exception) {
            System.out.println(
                "\nValidation correctly rejected bad telemetry: "
                    + exception.getMessage()
            );
        }
    }

    static final class OptionalDouble {
        private final boolean present;
        private final double value;

        private OptionalDouble(boolean present, double value) {
            this.present = present;
            this.value = value;
        }

        static OptionalDouble empty() {
            return new OptionalDouble(false, 0);
        }

        static OptionalDouble of(double value) {
            return new OptionalDouble(true, value);
        }

        boolean isEmpty() {
            return !present;
        }

        double getAsDouble() {
            if (!present) {
                throw new IllegalStateException("No metric average is available.");
            }
            return value;
        }
    }
}
