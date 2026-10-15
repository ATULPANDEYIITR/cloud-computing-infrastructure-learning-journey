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
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

/*
 * Enterprise serverless order-processing model.
 *
 * Java 17 or later:
 *   javac ServerlessEnterprise.java
 *   java ServerlessEnterprise
 *
 * This program focuses on typed domain modeling, dependency isolation,
 * concurrent execution, bounded capacity, retry classification, and
 * operational measurements.
 */
public class ServerlessEnterprise {

    enum TriggerType {
        HTTP_REQUEST,
        QUEUE_MESSAGE,
        OBJECT_CREATED,
        SCHEDULED_EVENT
    }

    enum InvocationStatus {
        ACCEPTED,
        SUCCEEDED,
        FAILED,
        TIMED_OUT,
        THROTTLED
    }

    record CloudEvent(
        String id,
        String source,
        String type,
        Map<String, Object> data,
        Instant occurredAt
    ) {
        CloudEvent {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Event ID is required.");
            }
            if (source == null || source.isBlank()) {
                throw new IllegalArgumentException("Event source is required.");
            }
            if (type == null || type.isBlank()) {
                throw new IllegalArgumentException("Event type is required.");
            }
            data = Collections.unmodifiableMap(new HashMap<>(data));
            Objects.requireNonNull(occurredAt, "occurredAt");
        }

        static CloudEvent create(
            String source,
            String type,
            Map<String, Object> data
        ) {
            return new CloudEvent(
                UUID.randomUUID().toString(),
                source,
                type,
                data,
                Instant.now()
            );
        }
    }

    record FunctionPolicy(
        String functionName,
        int memoryMb,
        long timeoutMillis,
        long initializationMillis,
        int maxConcurrency,
        int maxRetries,
        long idleTtlMillis
    ) {
        FunctionPolicy {
            if (functionName == null || functionName.isBlank()) {
                throw new IllegalArgumentException("Function name is required.");
            }
            if (memoryMb < 128) {
                throw new IllegalArgumentException("Memory must be at least 128 MB.");
            }
            if (timeoutMillis <= 0 || initializationMillis < 0) {
                throw new IllegalArgumentException("Invalid execution timing.");
            }
            if (maxConcurrency < 1 || maxRetries < 0 || idleTtlMillis < 0) {
                throw new IllegalArgumentException("Invalid runtime policy.");
            }
        }
    }

    record InvocationContext(
        String functionName,
        String environmentId,
        int memoryMb,
        int attempt,
        boolean coldStart
    ) {}

    record InvocationResult(
        String eventId,
        String functionName,
        InvocationStatus status,
        boolean coldStart,
        int attempts,
        long durationMillis,
        String message,
        Object value
    ) {}

    interface EventHandler {
        Object handle(CloudEvent event, InvocationContext context)
            throws Exception;
    }

    interface RetryPolicy {
        boolean shouldRetry(Exception exception, int completedAttempt);
    }

    static final class TransientDependencyException extends Exception {
        TransientDependencyException(String message) {
            super(message);
        }
    }

    static final class DefaultRetryPolicy implements RetryPolicy {
        @Override
        public boolean shouldRetry(Exception exception, int completedAttempt) {
            return exception instanceof TransientDependencyException;
        }
    }

    static final class ExecutionEnvironment {
        private final String id = UUID.randomUUID().toString().substring(0, 8);
        private final long createdAtMillis;
        private long lastUsedAtMillis;
        private boolean busy;
        private int successfulInvocations;

        ExecutionEnvironment(long now) {
            createdAtMillis = now;
            lastUsedAtMillis = now;
        }
    }

    static final class RuntimeMetrics {
        private int accepted;
        private int succeeded;
        private int failed;
        private int timedOut;
        private int throttled;
        private int retries;
        private int coldStarts;
        private long totalDurationMillis;
        private final List<Long> durations = new ArrayList<>();

        synchronized void recordSuccess(long duration) {
            succeeded++;
            totalDurationMillis += duration;
            durations.add(duration);
        }

        synchronized Map<String, Object> snapshot() {
            List<Long> sorted = new ArrayList<>(durations);
            Collections.sort(sorted);
            long p95 = sorted.isEmpty()
                ? 0
                : sorted.get((int) Math.ceil(sorted.size() * 0.95) - 1);

            double average = sorted.isEmpty()
                ? 0.0
                : (double) totalDurationMillis / sorted.size();

            Map<String, Object> values = new HashMap<>();
            values.put("accepted", accepted);
            values.put("succeeded", succeeded);
            values.put("failed", failed);
            values.put("timedOut", timedOut);
            values.put("throttled", throttled);
            values.put("retries", retries);
            values.put("coldStarts", coldStarts);
            values.put("averageDurationMillis", average);
            values.put("p95DurationMillis", p95);
            return Map.copyOf(values);
        }
    }

    static final class ServerlessRuntime implements AutoCloseable {
        private final FunctionPolicy policy;
        private final EventHandler handler;
        private final RetryPolicy retryPolicy;
        private final ExecutorService executor;
        private final AtomicInteger activeInvocations = new AtomicInteger();
        private final List<ExecutionEnvironment> environments = new ArrayList<>();
        private final RuntimeMetrics metrics = new RuntimeMetrics();

        ServerlessRuntime(
            FunctionPolicy policy,
            EventHandler handler,
            RetryPolicy retryPolicy
        ) {
            this.policy = Objects.requireNonNull(policy);
            this.handler = Objects.requireNonNull(handler);
            this.retryPolicy = Objects.requireNonNull(retryPolicy);

            // A fixed-size executor bounds simultaneous handler executions.
            this.executor = Executors.newFixedThreadPool(policy.maxConcurrency());
        }

        InvocationResult invoke(CloudEvent event) {
            synchronized (metrics) {
                metrics.accepted++;
            }

            long invocationStarted = System.nanoTime();
            int attempts = 0;
            boolean anyColdStart = false;
            String lastError = "Unknown execution failure";

            for (int attempt = 1; attempt <= policy.maxRetries() + 1; attempt++) {
                attempts = attempt;
                Optional<ExecutionEnvironment> lease = acquireEnvironment();

                if (lease.isEmpty()) {
                    synchronized (metrics) {
                        metrics.throttled++;
                    }
                    return new InvocationResult(
                        event.id(),
                        policy.functionName(),
                        InvocationStatus.THROTTLED,
                        anyColdStart,
                        attempts,
                        elapsedMillis(invocationStarted),
                        "Concurrency limit reached",
                        null
                    );
                }

                ExecutionEnvironment environment = lease.get();
                boolean coldStart = environment.successfulInvocations == 0;
                anyColdStart |= coldStart;

                if (coldStart) {
                    synchronized (metrics) {
                        metrics.coldStarts++;
                    }
                }

                Callable<Object> task = () -> {
                    if (coldStart && policy.initializationMillis() > 0) {
                        Thread.sleep(policy.initializationMillis());
                    }

                    InvocationContext context = new InvocationContext(
                        policy.functionName(),
                        environment.id,
                        policy.memoryMb(),
                        attempt,
                        coldStart
                    );

                    return handler.handle(event, context);
                };

                Future<Object> future = executor.submit(task);

                try {
                    Object value = future.get(
                        policy.timeoutMillis(),
                        TimeUnit.MILLISECONDS
                    );

                    long duration = elapsedMillis(invocationStarted);
                    environment.successfulInvocations++;

                    synchronized (metrics) {
                        metrics.recordSuccess(duration);
                    }

                    return new InvocationResult(
                        event.id(),
                        policy.functionName(),
                        InvocationStatus.SUCCEEDED,
                        anyColdStart,
                        attempts,
                        duration,
                        "Execution completed",
                        value
                    );
                } catch (TimeoutException exception) {
                    future.cancel(true);
                    lastError = "Execution exceeded timeout";
                    synchronized (metrics) {
                        metrics.timedOut++;
                    }
                    break;
                } catch (InterruptedException exception) {
                    future.cancel(true);
                    Thread.currentThread().interrupt();
                    lastError = "Invocation thread was interrupted";
                    break;
                } catch (ExecutionException exception) {
                    Throwable cause = exception.getCause();
                    Exception handlerError = cause instanceof Exception
                        ? (Exception) cause
                        : new RuntimeException(cause);

                    lastError = handlerError.getMessage() == null
                        ? handlerError.getClass().getSimpleName()
                        : handlerError.getMessage();

                    if (
                        attempt < policy.maxRetries() + 1 &&
                        retryPolicy.shouldRetry(handlerError, attempt)
                    ) {
                        synchronized (metrics) {
                            metrics.retries++;
                        }
                    } else {
                        break;
                    }
                } finally {
                    releaseEnvironment(environment);
                }
            }

            synchronized (metrics) {
                metrics.failed++;
            }

            return new InvocationResult(
                event.id(),
                policy.functionName(),
                InvocationStatus.FAILED,
                anyColdStart,
                attempts,
                elapsedMillis(invocationStarted),
                lastError,
                null
            );
        }

        private synchronized Optional<ExecutionEnvironment> acquireEnvironment() {
            long now = System.currentTimeMillis();

            environments.removeIf(environment ->
                !environment.busy &&
                now - environment.lastUsedAtMillis > policy.idleTtlMillis()
            );

            for (ExecutionEnvironment environment : environments) {
                if (!environment.busy) {
                    environment.busy = true;
                    activeInvocations.incrementAndGet();
                    return Optional.of(environment);
                }
            }

            if (environments.size() >= policy.maxConcurrency()) {
                return Optional.empty();
            }

            ExecutionEnvironment environment = new ExecutionEnvironment(now);
            environment.busy = true;
            environments.add(environment);
            activeInvocations.incrementAndGet();
            return Optional.of(environment);
        }

        private synchronized void releaseEnvironment(
            ExecutionEnvironment environment
        ) {
            environment.busy = false;
            environment.lastUsedAtMillis = System.currentTimeMillis();
            activeInvocations.decrementAndGet();
        }

        Map<String, Object> metrics() {
            return metrics.snapshot();
        }

        int environmentCount() {
            synchronized (this) {
                return environments.size();
            }
        }

        private static long elapsedMillis(long startedAtNanos) {
            return TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startedAtNanos
            );
        }

        @Override
        public void close() {
            executor.shutdownNow();
        }
    }

    static final class EventRouter {
        private final Map<String, List<ServerlessRuntime>> routes = new HashMap<>();
        private final List<InvocationResult> deadLetters = new ArrayList<>();

        void subscribe(String eventType, ServerlessRuntime runtime) {
            routes.computeIfAbsent(eventType, ignored -> new ArrayList<>())
                .add(runtime);
        }

        List<InvocationResult> publish(CloudEvent event) {
            List<ServerlessRuntime> subscribers = routes.get(event.type());

            if (subscribers == null || subscribers.isEmpty()) {
                InvocationResult unrouted = new InvocationResult(
                    event.id(),
                    "unrouted",
                    InvocationStatus.FAILED,
                    false,
                    0,
                    0,
                    "No subscription for event type " + event.type(),
                    null
                );
                deadLetters.add(unrouted);
                return List.of(unrouted);
            }

            List<InvocationResult> results = new ArrayList<>();

            for (ServerlessRuntime runtime : subscribers) {
                InvocationResult result = runtime.invoke(event);
                results.add(result);

                if (
                    result.status() == InvocationStatus.FAILED ||
                    result.status() == InvocationStatus.TIMED_OUT ||
                    result.status() == InvocationStatus.THROTTLED
                ) {
                    deadLetters.add(result);
                }
            }

            return List.copyOf(results);
        }

        List<InvocationResult> deadLetters() {
            return List.copyOf(deadLetters);
        }
    }

    static Object validateOrder(
        CloudEvent event,
        InvocationContext context
    ) {
        Object orderId = event.data().get("orderId");
        Object rawAmount = event.data().get("amount");

        if (!(orderId instanceof String id) || id.isBlank()) {
            throw new IllegalArgumentException("A non-empty orderId is required.");
        }

        if (!(rawAmount instanceof Number number)) {
            throw new IllegalArgumentException("amount must be numeric.");
        }

        double amount = number.doubleValue();
        if (!Double.isFinite(amount) || amount <= 0.0) {
            throw new IllegalArgumentException(
                "amount must be finite and positive."
            );
        }

        return Map.of(
            "orderId", id,
            "amount", amount,
            "state", "validated",
            "environmentId", context.environmentId(),
            "coldStart", context.coldStart()
        );
    }

    static Object recordAudit(
        CloudEvent event,
        InvocationContext context
    ) {
        return Map.of(
            "eventId", event.id(),
            "eventType", event.type(),
            "receivedAt", Instant.now().toString(),
            "environmentId", context.environmentId()
        );
    }

    public static void main(String[] args) {
        RetryPolicy retryPolicy = new DefaultRetryPolicy();

        try (
            ServerlessRuntime orderRuntime = new ServerlessRuntime(
                new FunctionPolicy(
                    "enterprise-order-validator",
                    512,
                    1200,
                    50,
                    4,
                    2,
                    300_000
                ),
                ServerlessEnterprise::validateOrder,
                retryPolicy
            );
            ServerlessRuntime auditRuntime = new ServerlessRuntime(
                new FunctionPolicy(
                    "enterprise-audit-writer",
                    128,
                    600,
                    10,
                    8,
                    0,
                    300_000
                ),
                ServerlessEnterprise::recordAudit,
                retryPolicy
            )
        ) {
            EventRouter router = new EventRouter();
            router.subscribe("order.created", orderRuntime);
            router.subscribe("order.created", auditRuntime);

            List<CloudEvent> events = List.of(
                CloudEvent.create(
                    "checkout-service",
                    "order.created",
                    Map.of("orderId", "ORD-8101", "amount", 1500.0)
                ),
                CloudEvent.create(
                    "checkout-service",
                    "order.created",
                    Map.of("orderId", "ORD-8102", "amount", -25.0)
                ),
                CloudEvent.create(
                    "checkout-service",
                    "order.created",
                    Map.of("orderId", "ORD-8103", "amount", 850.5)
                )
            );

            for (CloudEvent event : events) {
                System.out.println("\nEvent " + event.id());

                for (InvocationResult result : router.publish(event)) {
                    System.out.printf(
                        "function=%s status=%s coldStart=%s attempts=%d "
                            + "durationMs=%d message=%s%n",
                        result.functionName(),
                        result.status(),
                        result.coldStart(),
                        result.attempts(),
                        result.durationMillis(),
                        result.message()
                    );

                    if (result.value() != null) {
                        System.out.println("value=" + result.value());
                    }
                }
            }

            System.out.println("\nOrder runtime metrics: " + orderRuntime.metrics());
            System.out.println("Audit runtime metrics: " + auditRuntime.metrics());
            System.out.println(
                "Order execution environments: " + orderRuntime.environmentCount()
            );

            System.out.println("\nDead-letter results");
            for (InvocationResult result : router.deadLetters()) {
                System.out.println(result);
            }

            // A real multi-instance idempotency implementation must use
            // durable shared storage with an atomic uniqueness constraint.
            // A Java collection cannot guarantee cross-process deduplication.
        }
    }
}
