import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/**
 * Enterprise-oriented cloud load-balancer governance model.
 *
 * The domain separates:
 * - load-balancer type
 * - listener
 * - target group
 * - target health
 * - health-check policy
 * - routing behavior
 *
 * Java 17 records are used for immutable request and listener data.
 */
public class CloudLoadBalancer {

    enum LoadBalancerType {
        APPLICATION,
        NETWORK
    }

    enum Protocol {
        HTTP,
        HTTPS,
        TCP,
        TLS
    }

    enum TargetState {
        HEALTHY,
        UNHEALTHY,
        DRAINING
    }

    enum HealthStatus {
        PASS,
        FAIL
    }

    static final class ConfigurationException extends RuntimeException {
        ConfigurationException(String message) {
            super(message);
        }
    }

    static final class RoutingException extends RuntimeException {
        RoutingException(String message) {
            super(message);
        }
    }

    record HealthCheckPolicy(
        Protocol protocol,
        int port,
        Optional<String> path,
        int intervalSeconds,
        int timeoutSeconds,
        int healthyThreshold,
        int unhealthyThreshold
    ) {
        HealthCheckPolicy {
            Objects.requireNonNull(protocol);
            Objects.requireNonNull(path);

            if (port < 1 || port > 65535) {
                throw new ConfigurationException("Invalid health-check port.");
            }

            if ((protocol == Protocol.HTTP || protocol == Protocol.HTTPS)
                    && path.isEmpty()) {
                throw new ConfigurationException(
                    "HTTP health checks require a path."
                );
            }

            if (intervalSeconds <= 0 || timeoutSeconds <= 0) {
                throw new ConfigurationException(
                    "Health-check timings must be positive."
                );
            }

            if (timeoutSeconds >= intervalSeconds) {
                throw new ConfigurationException(
                    "Health-check timeout must be shorter than interval."
                );
            }

            if (healthyThreshold <= 0 || unhealthyThreshold <= 0) {
                throw new ConfigurationException(
                    "Health thresholds must be positive."
                );
            }
        }
    }

    static final class Target {
        private final String id;
        private final String address;
        private final int port;
        private final String availabilityZone;
        private TargetState state;
        private int activeConnections;

        Target(
            String id,
            String address,
            int port,
            String availabilityZone
        ) {
            if (id == null || id.isBlank()) {
                throw new ConfigurationException("Target ID is required.");
            }

            if (address == null || address.isBlank()) {
                throw new ConfigurationException("Target address is required.");
            }

            if (port < 1 || port > 65535) {
                throw new ConfigurationException("Target port is invalid.");
            }

            this.id = id;
            this.address = address;
            this.port = port;
            this.availabilityZone = Objects.requireNonNull(availabilityZone);
            this.state = TargetState.HEALTHY;
        }

        String id() {
            return id;
        }

        String address() {
            return address;
        }

        int port() {
            return port;
        }

        String availabilityZone() {
            return availabilityZone;
        }

        TargetState state() {
            return state;
        }

        int activeConnections() {
            return activeConnections;
        }

        boolean acceptsNewConnections() {
            return state == TargetState.HEALTHY;
        }

        void applyHealthStatus(HealthStatus status) {
            state = status == HealthStatus.PASS
                ? TargetState.HEALTHY
                : TargetState.UNHEALTHY;
        }

        void drain() {
            state = TargetState.DRAINING;
        }

        void openConnection() {
            if (!acceptsNewConnections()) {
                throw new RoutingException(
                    "Target cannot accept a new connection."
                );
            }
            activeConnections++;
        }

        void closeConnection() {
            if (activeConnections == 0) {
                throw new RoutingException(
                    "Target has no active connections."
                );
            }
            activeConnections--;
        }
    }

    static final class TargetGroup {
        private final String name;
        private final Protocol protocol;
        private final int port;
        private final HealthCheckPolicy healthCheck;
        private final Map<String, Target> targets = new HashMap<>();

        TargetGroup(
            String name,
            Protocol protocol,
            int port,
            HealthCheckPolicy healthCheck
        ) {
            if (name == null || name.isBlank()) {
                throw new ConfigurationException(
                    "Target-group name is required."
                );
            }

            if (port < 1 || port > 65535) {
                throw new ConfigurationException(
                    "Target-group port is invalid."
                );
            }

            this.name = name;
            this.protocol = Objects.requireNonNull(protocol);
            this.port = port;
            this.healthCheck = Objects.requireNonNull(healthCheck);
        }

        String name() {
            return name;
        }

        Protocol protocol() {
            return protocol;
        }

        int port() {
            return port;
        }

        HealthCheckPolicy healthCheck() {
            return healthCheck;
        }

        void register(Target target) {
            if (targets.containsKey(target.id())) {
                throw new ConfigurationException(
                    "Duplicate target: " + target.id()
                );
            }

            if (target.port() != port) {
                throw new ConfigurationException(
                    "Target port does not match target-group port."
                );
            }

            targets.put(target.id(), target);
        }

        Target target(String id) {
            Target target = targets.get(id);
            if (target == null) {
                throw new RoutingException(
                    "Unknown target: " + id
                );
            }
            return target;
        }

        List<Target> healthyTargets() {
            return targets.values()
                .stream()
                .filter(Target::acceptsNewConnections)
                .toList();
        }

        Map<String, TargetState> states() {
            Map<String, TargetState> result = new HashMap<>();

            targets.values().forEach(
                target -> result.put(target.id(), target.state())
            );

            return Collections.unmodifiableMap(result);
        }
    }

    record Listener(
        Protocol protocol,
        int port,
        String targetGroup
    ) {
        Listener {
            Objects.requireNonNull(protocol);
            Objects.requireNonNull(targetGroup);

            if (port < 1 || port > 65535) {
                throw new ConfigurationException(
                    "Listener port is invalid."
                );
            }
        }
    }

    record ClientRequest(
        String id,
        Protocol protocol,
        int listenerPort,
        String sourceAddress,
        int sourcePort,
        String host,
        String path
    ) {
        ClientRequest {
            Objects.requireNonNull(id);
            Objects.requireNonNull(protocol);
        }
    }

    record RouteResult(
        String requestId,
        String targetId,
        String targetAddress,
        int targetPort
    ) {}

    interface RoutingPolicy {
        Target choose(
            ClientRequest request,
            List<Target> candidates
        );
    }

    static final class RoundRobinPolicy implements RoutingPolicy {
        private int nextIndex;

        @Override
        public Target choose(
            ClientRequest request,
            List<Target> candidates
        ) {
            if (candidates.isEmpty()) {
                throw new RoutingException(
                    "No healthy targets are available."
                );
            }

            Target target = candidates.get(
                nextIndex % candidates.size()
            );

            nextIndex++;
            return target;
        }
    }

    static final class FlowHashPolicy implements RoutingPolicy {
        @Override
        public Target choose(
            ClientRequest request,
            List<Target> candidates
        ) {
            if (candidates.isEmpty()) {
                throw new RoutingException(
                    "No healthy targets are available."
                );
            }

            String flowKey = String.join(
                "|",
                request.sourceAddress(),
                Integer.toString(request.sourcePort()),
                request.protocol().name(),
                Integer.toString(request.listenerPort())
            );

            int hash = flowKey.hashCode();
            int index = Math.floorMod(hash, candidates.size());

            return candidates.get(index);
        }
    }

    static final class HealthService {
        void applyProbe(
            TargetGroup group,
            String targetId,
            HealthStatus result
        ) {
            Target target = group.target(targetId);
            target.applyHealthStatus(result);
        }
    }

    static final class MergeLikeRoutingService {
        private final LoadBalancerType type;
        private final Map<String, TargetGroup> targetGroups =
            new HashMap<>();
        private final Map<String, Listener> listeners =
            new HashMap<>();
        private final Map<Protocol, RoutingPolicy> policies =
            new EnumMap<>(Protocol.class);

        MergeLikeRoutingService(LoadBalancerType type) {
            this.type = Objects.requireNonNull(type);

            if (type == LoadBalancerType.APPLICATION) {
                policies.put(Protocol.HTTP, new RoundRobinPolicy());
                policies.put(Protocol.HTTPS, new RoundRobinPolicy());
            } else {
                policies.put(Protocol.TCP, new FlowHashPolicy());
                policies.put(Protocol.TLS, new FlowHashPolicy());
            }
        }

        void registerTargetGroup(TargetGroup group) {
            if (targetGroups.containsKey(group.name())) {
                throw new ConfigurationException(
                    "Duplicate target group."
                );
            }

            targetGroups.put(group.name(), group);
        }

        void registerListener(Listener listener) {
            String key = listener.protocol() + ":" + listener.port();

            if (listeners.containsKey(key)) {
                throw new ConfigurationException(
                    "Duplicate listener."
                );
            }

            if (!targetGroups.containsKey(listener.targetGroup())) {
                throw new ConfigurationException(
                    "Listener references unknown target group."
                );
            }

            listeners.put(key, listener);
        }

        RouteResult route(ClientRequest request) {
            String key =
                request.protocol() + ":" + request.listenerPort();

            Listener listener = listeners.get(key);

            if (listener == null) {
                throw new RoutingException(
                    "No listener exists for " + key
                );
            }

            TargetGroup group =
                targetGroups.get(listener.targetGroup());

            if (group == null) {
                throw new RoutingException(
                    "Target group is unavailable."
                );
            }

            if (type == LoadBalancerType.APPLICATION &&
                request.protocol() != Protocol.HTTP &&
                request.protocol() != Protocol.HTTPS) {
                throw new RoutingException(
                    "Application load balancers require HTTP/HTTPS."
                );
            }

            if (type == LoadBalancerType.NETWORK &&
                request.protocol() != Protocol.TCP &&
                request.protocol() != Protocol.TLS) {
                throw new RoutingException(
                    "Network load balancers require TCP/TLS."
                );
            }

            List<Target> healthy = group.healthyTargets();

            RoutingPolicy policy = policies.get(request.protocol());

            if (policy == null) {
                throw new RoutingException(
                    "No routing policy exists for protocol."
                );
            }

            Target selected = policy.choose(request, healthy);
            selected.openConnection();

            return new RouteResult(
                request.id(),
                selected.id(),
                selected.address(),
                selected.port()
            );
        }

        void drain(String groupName, String targetId) {
            TargetGroup group = targetGroups.get(groupName);

            if (group == null) {
                throw new RoutingException(
                    "Unknown target group."
                );
            }

            group.target(targetId).drain();
        }

        void closeConnection(
            String groupName,
            String targetId
        ) {
            TargetGroup group = targetGroups.get(groupName);

            if (group == null) {
                throw new RoutingException(
                    "Unknown target group."
                );
            }

            group.target(targetId).closeConnection();
        }

        Map<String, TargetState> healthReport(
            String groupName
        ) {
            TargetGroup group = targetGroups.get(groupName);

            if (group == null) {
                throw new RoutingException(
                    "Unknown target group."
                );
            }

            return group.states();
        }
    }

    private static TargetGroup createWebTargetGroup() {
        HealthCheckPolicy healthCheck = new HealthCheckPolicy(
            Protocol.HTTP,
            8080,
            Optional.of("/health"),
            10,
            3,
            2,
            3
        );

        TargetGroup group = new TargetGroup(
            "web-targets",
            Protocol.HTTP,
            8080,
            healthCheck
        );

        group.register(
            new Target("web-a", "10.0.1.10", 8080, "zone-a")
        );
        group.register(
            new Target("web-b", "10.0.2.10", 8080, "zone-b")
        );
        group.register(
            new Target("web-c", "10.0.3.10", 8080, "zone-c")
        );

        return group;
    }

    private static TargetGroup createTcpTargetGroup() {
        HealthCheckPolicy healthCheck = new HealthCheckPolicy(
            Protocol.TCP,
            9000,
            Optional.empty(),
            10,
            3,
            2,
            3
        );

        TargetGroup group = new TargetGroup(
            "tcp-targets",
            Protocol.TCP,
            9000,
            healthCheck
        );

        group.register(
            new Target("tcp-a", "10.1.1.10", 9000, "zone-a")
        );
        group.register(
            new Target("tcp-b", "10.1.2.10", 9000, "zone-b")
        );

        return group;
    }

    public static void main(String[] args) {
        MergeLikeRoutingService application =
            new MergeLikeRoutingService(
                LoadBalancerType.APPLICATION
            );

        application.registerTargetGroup(
            createWebTargetGroup()
        );

        application.registerListener(
            new Listener(
                Protocol.HTTP,
                80,
                "web-targets"
            )
        );

        System.out.println("Application load balancing");

        List<ClientRequest> webRequests = List.of(
            new ClientRequest(
                "req-1",
                Protocol.HTTP,
                80,
                "192.0.2.10",
                50001,
                "api.example.com",
                "/users"
            ),
            new ClientRequest(
                "req-2",
                Protocol.HTTP,
                80,
                "192.0.2.11",
                50002,
                "api.example.com",
                "/orders"
            ),
            new ClientRequest(
                "req-3",
                Protocol.HTTP,
                80,
                "192.0.2.12",
                50003,
                "api.example.com",
                "/orders/42"
            )
        );

        for (ClientRequest request : webRequests) {
            System.out.println(application.route(request));
        }

        HealthService healthService = new HealthService();

        healthService.applyProbe(
            application.targetGroups.get("web-targets"),
            "web-b",
            HealthStatus.FAIL
        );

        System.out.println(
            "Health state: " +
            application.healthReport("web-targets")
        );

        MergeLikeRoutingService network =
            new MergeLikeRoutingService(
                LoadBalancerType.NETWORK
            );

        network.registerTargetGroup(
            createTcpTargetGroup()
        );

        network.registerListener(
            new Listener(
                Protocol.TCP,
                443,
                "tcp-targets"
            )
        );

        System.out.println("\nNetwork load balancing");

        ClientRequest stableFlow = new ClientRequest(
            "flow-1",
            Protocol.TCP,
            443,
            "198.51.100.10",
            51001,
            "",
            ""
        );

        RouteResult first = network.route(stableFlow);
        RouteResult repeated = network.route(stableFlow);

        System.out.println("First selection: " + first.targetId());
        System.out.println("Repeated selection: " + repeated.targetId());

        network.drain("tcp-targets", first.targetId());

        try {
            RouteResult next = network.route(
                new ClientRequest(
                    "flow-2",
                    Protocol.TCP,
                    443,
                    "198.51.100.11",
                    51002,
                    "",
                    ""
                )
            );

            System.out.println(
                "New flow after draining: " +
                next.targetId()
            );
        } catch (RoutingException error) {
            System.err.println(
                "Routing failed: " + error.getMessage()
            );
        }
    }
}
