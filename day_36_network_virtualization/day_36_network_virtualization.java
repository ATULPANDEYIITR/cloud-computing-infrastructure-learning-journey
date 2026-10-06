import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/*
 * Enterprise Network Virtualization Governance
 *
 * Java 17 implementation of a virtual data-center network model.
 *
 * The domain model separates:
 * - virtual network definitions
 * - virtual machines and NICs
 * - switching and forwarding
 * - overlay tunnels
 * - SDN policies
 * - routing and merge-like policy evaluation
 *
 * No external dependencies are required.
 */
public class NetworkVirtualizationEnterprise {

    enum NetworkType {
        FRONTEND,
        BACKEND,
        DATABASE
    }

    enum PolicyDecision {
        ALLOW,
        DENY
    }

    enum PortState {
        UP,
        DOWN
    }

    record IPv4(String value) {
        IPv4 {
            String[] parts = value.split("\\.");

            if (parts.length != 4) {
                throw new IllegalArgumentException(
                    "Invalid IPv4 address: " + value
                );
            }

            for (String part : parts) {
                int number;

                try {
                    number = Integer.parseInt(part);
                } catch (NumberFormatException exception) {
                    throw new IllegalArgumentException(
                        "Invalid IPv4 address: " + value,
                        exception
                    );
                }

                if (number < 0 || number > 255) {
                    throw new IllegalArgumentException(
                        "IPv4 octet outside range: " + value
                    );
                }
            }
        }
    }

    record MacAddress(String value) {
        MacAddress {
            if (!value.matches("([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}")) {
                throw new IllegalArgumentException(
                    "Invalid MAC address: " + value
                );
            }

            value = value.toLowerCase();
        }
    }

    record Cidr(String network, int prefixLength) {
        Cidr {
            if (prefixLength < 0 || prefixLength > 32) {
                throw new IllegalArgumentException(
                    "CIDR prefix must be between 0 and 32"
                );
            }
        }

        private long ipv4ToLong(String ip) {
            String[] parts = ip.split("\\.");
            long value = 0;

            for (String part : parts) {
                value = (value << 8) | Integer.parseInt(part);
            }

            return value;
        }

        boolean contains(IPv4 address) {
            if (prefixLength == 0) {
                return true;
            }

            long addressValue = ipv4ToLong(address.value());
            long networkValue = ipv4ToLong(network);

            long mask =
                0xffffffffL << (32 - prefixLength);

            return (addressValue & mask) ==
                   (networkValue & mask);
        }
    }

    record VirtualNetwork(
        String name,
        NetworkType type,
        Cidr subnet,
        int vlanId,
        int vni,
        IPv4 gateway,
        boolean isolated
    ) {
        VirtualNetwork {
            if (vlanId < 1 || vlanId > 4094) {
                throw new IllegalArgumentException(
                    "VLAN ID must be between 1 and 4094"
                );
            }

            if (vni < 1 || vni > 16_777_215) {
                throw new IllegalArgumentException(
                    "VNI must fit into 24 bits"
                );
            }
        }
    }

    record VirtualNic(
        String name,
        MacAddress mac,
        IPv4 address,
        String networkName
    ) {
    }

    record VirtualMachine(
        String name,
        Map<String, VirtualNic> nics
    ) {
        VirtualMachine {
            nics = new LinkedHashMap<>(nics);
        }

        VirtualNic nic(String name) {
            VirtualNic nic = nics.get(name);

            if (nic == null) {
                throw new IllegalArgumentException(
                    "NIC does not exist: " + name
                );
            }

            return nic;
        }
    }

    record EthernetFrame(
        MacAddress sourceMac,
        MacAddress destinationMac,
        IPv4 sourceIp,
        IPv4 destinationIp,
        String payload,
        Integer vlanId,
        int ttl
    ) {
        EthernetFrame {
            if (ttl < 0 || ttl > 255) {
                throw new IllegalArgumentException(
                    "TTL must be between 0 and 255"
                );
            }
        }

        EthernetFrame decrementTtl() {
            if (ttl <= 1) {
                throw new IllegalStateException(
                    "Cannot forward packet with expired TTL"
                );
            }

            return new EthernetFrame(
                sourceMac,
                destinationMac,
                sourceIp,
                destinationIp,
                payload,
                vlanId,
                ttl - 1
            );
        }
    }

    record OverlayPacket(
        String outerSource,
        String outerDestination,
        int vni,
        EthernetFrame innerFrame
    ) {
        OverlayPacket {
            if (vni < 1 || vni > 16_777_215) {
                throw new IllegalArgumentException(
                    "Invalid overlay VNI"
                );
            }
        }
    }

    record NetworkPolicy(
        String sourceNetwork,
        String destinationNetwork,
        PolicyDecision decision
    ) {
    }

    static final class PolicyConflictException
        extends RuntimeException {

        PolicyConflictException(String message) {
            super(message);
        }
    }

    static final class NetworkPolicyEngine {

        private final Map<String, NetworkPolicy> policies =
            new HashMap<>();

        void register(NetworkPolicy policy) {
            String key = key(
                policy.sourceNetwork(),
                policy.destinationNetwork()
            );

            NetworkPolicy existing = policies.putIfAbsent(
                key,
                policy
            );

            if (existing != null &&
                existing.decision() != policy.decision()) {
                throw new PolicyConflictException(
                    "Conflicting policy for " + key
                );
            }
        }

        PolicyDecision evaluate(
            String sourceNetwork,
            String destinationNetwork
        ) {
            return Optional.ofNullable(
                    policies.get(
                        key(sourceNetwork, destinationNetwork)
                    )
                )
                .map(NetworkPolicy::decision)
                .orElse(PolicyDecision.DENY);
        }

        private static String key(
            String source,
            String destination
        ) {
            return source + "->" + destination;
        }
    }

    static final class VirtualSwitch {

        record Port(
            String name,
            PortState state
        ) {
        }

        private final String name;

        private final Map<String, Port> ports =
            new LinkedHashMap<>();

        private final Map<MacAddress, String> macTable =
            new LinkedHashMap<>();

        private long forwardedFrames;
        private long floodedFrames;
        private long droppedFrames;

        VirtualSwitch(String name) {
            this.name = Objects.requireNonNull(name);
        }

        void addPort(String name) {
            if (ports.containsKey(name)) {
                throw new IllegalArgumentException(
                    "Duplicate switch port: " + name
                );
            }

            ports.put(
                name,
                new Port(name, PortState.UP)
            );
        }

        void setPortState(String name, PortState state) {
            if (!ports.containsKey(name)) {
                throw new IllegalArgumentException(
                    "Unknown switch port: " + name
                );
            }

            ports.put(
                name,
                new Port(name, state)
            );
        }

        List<String> forward(
            EthernetFrame frame,
            String ingressPort
        ) {
            Port ingress = ports.get(ingressPort);

            if (ingress == null ||
                ingress.state() != PortState.UP) {
                droppedFrames++;
                return List.of();
            }

            /*
             * MAC learning associates the source address with the ingress
             * port. The table is data-plane state, not centralized policy.
             */
            macTable.put(
                frame.sourceMac(),
                ingressPort
            );

            String destinationPort =
                macTable.get(frame.destinationMac());

            if (destinationPort != null) {
                if (destinationPort.equals(ingressPort)) {
                    return List.of();
                }

                Port output = ports.get(destinationPort);

                if (output == null ||
                    output.state() != PortState.UP) {
                    droppedFrames++;
                    return List.of();
                }

                forwardedFrames++;
                return List.of(destinationPort);
            }

            List<String> floodTargets = ports.values()
                .stream()
                .filter(
                    port ->
                        !port.name().equals(ingressPort) &&
                        port.state() == PortState.UP
                )
                .map(Port::name)
                .toList();

            floodedFrames += floodTargets.size();

            return floodTargets;
        }

        Map<MacAddress, String> macTable() {
            return Collections.unmodifiableMap(macTable);
        }

        void printStatistics() {
            System.out.printf(
                "%s forwarded=%d flooded=%d dropped=%d%n",
                name,
                forwardedFrames,
                floodedFrames,
                droppedFrames
            );
        }
    }

    static final class VirtualRouter {

        private final Map<String, VirtualNetwork> networks;
        private final NetworkPolicyEngine policyEngine;

        VirtualRouter(
            Map<String, VirtualNetwork> networks,
            NetworkPolicyEngine policyEngine
        ) {
            this.networks = networks;
            this.policyEngine = policyEngine;
        }

        Optional<VirtualNetwork> locateNetwork(
            IPv4 destination
        ) {
            return networks.values()
                .stream()
                .filter(
                    network ->
                        network.subnet().contains(destination)
                )
                .sorted(
                    (left, right) ->
                        Integer.compare(
                            right.subnet().prefixLength(),
                            left.subnet().prefixLength()
                        )
                )
                .findFirst();
        }

        EthernetFrame route(
            EthernetFrame frame,
            String sourceNetwork
        ) {
            if (frame.ttl() <= 1) {
                throw new IllegalStateException(
                    "TTL expired before routing"
                );
            }

            VirtualNetwork destinationNetwork =
                locateNetwork(frame.destinationIp())
                    .orElseThrow(
                        () ->
                            new IllegalStateException(
                                "No virtual route to " +
                                frame.destinationIp().value()
                            )
                    );

            PolicyDecision decision =
                policyEngine.evaluate(
                    sourceNetwork,
                    destinationNetwork.name()
                );

            if (decision != PolicyDecision.ALLOW) {
                throw new SecurityException(
                    "Policy denied " +
                    sourceNetwork +
                    " -> " +
                    destinationNetwork.name()
                );
            }

            return frame.decrementTtl();
        }
    }

    static final class OverlayFabric {

        private final Map<MacAddress, String> endpointDatabase =
            new HashMap<>();

        void registerEndpoint(
            MacAddress mac,
            String vtep
        ) {
            endpointDatabase.put(mac, vtep);
        }

        OverlayPacket encapsulate(
            EthernetFrame frame,
            String sourceVtep,
            String destinationVtep,
            int vni
        ) {
            if (!endpointDatabase.containsKey(
                    frame.destinationMac()
                )) {
                throw new IllegalStateException(
                    "Unknown remote overlay endpoint"
                );
            }

            return new OverlayPacket(
                sourceVtep,
                destinationVtep,
                vni,
                frame
            );
        }

        EthernetFrame decapsulate(
            OverlayPacket packet,
            int expectedVni
        ) {
            if (packet.vni() != expectedVni) {
                throw new SecurityException(
                    "Overlay segment mismatch"
                );
            }

            return packet.innerFrame();
        }
    }

    static final class RepositoryNetworkService {

        private final Map<String, VirtualNetwork> networks =
            new LinkedHashMap<>();

        private final Map<String, VirtualMachine> machines =
            new LinkedHashMap<>();

        private final NetworkPolicyEngine policyEngine =
            new NetworkPolicyEngine();

        private final VirtualSwitch virtualSwitch =
            new VirtualSwitch("vswitch-enterprise");

        private VirtualRouter router;

        private final OverlayFabric overlay =
            new OverlayFabric();

        void initialize() {
            registerNetworks();
            registerMachines();
            registerPolicies();

            router =
                new VirtualRouter(
                    networks,
                    policyEngine
                );
        }

        private void registerNetworks() {
            register(
                new VirtualNetwork(
                    "frontend",
                    NetworkType.FRONTEND,
                    new Cidr("10.10.10.0", 24),
                    110,
                    5001,
                    new IPv4("10.10.10.1"),
                    false
                )
            );

            register(
                new VirtualNetwork(
                    "backend",
                    NetworkType.BACKEND,
                    new Cidr("10.10.20.0", 24),
                    120,
                    5002,
                    new IPv4("10.10.20.1"),
                    false
                )
            );

            register(
                new VirtualNetwork(
                    "database",
                    NetworkType.DATABASE,
                    new Cidr("10.10.30.0", 24),
                    130,
                    5003,
                    new IPv4("10.10.30.1"),
                    true
                )
            );
        }

        private void register(VirtualNetwork network) {
            if (networks.putIfAbsent(
                    network.name(),
                    network
                ) != null) {
                throw new IllegalStateException(
                    "Duplicate virtual network"
                );
            }
        }

        private void registerMachines() {
            VirtualMachine web =
                new VirtualMachine(
                    "web-01",
                    Map.of(
                        "eth0",
                        new VirtualNic(
                            "eth0",
                            new MacAddress(
                                "02:00:00:00:10:01"
                            ),
                            new IPv4("10.10.10.10"),
                            "frontend"
                        )
                    )
                );

            VirtualMachine app =
                new VirtualMachine(
                    "app-01",
                    Map.of(
                        "eth0",
                        new VirtualNic(
                            "eth0",
                            new MacAddress(
                                "02:00:00:00:20:01"
                            ),
                            new IPv4("10.10.20.10"),
                            "backend"
                        )
                    )
                );

            VirtualMachine database =
                new VirtualMachine(
                    "db-01",
                    Map.of(
                        "eth0",
                        new VirtualNic(
                            "eth0",
                            new MacAddress(
                                "02:00:00:00:30:01"
                            ),
                            new IPv4("10.10.30.10"),
                            "database"
                        )
                    )
                );

            machines.put(web.name(), web);
            machines.put(app.name(), app);
            machines.put(database.name(), database);

            virtualSwitch.addPort("web-port");
            virtualSwitch.addPort("app-port");
            virtualSwitch.addPort("overlay-uplink");

            overlay.registerEndpoint(
                web.nic("eth0").mac(),
                "192.0.2.10"
            );

            overlay.registerEndpoint(
                app.nic("eth0").mac(),
                "192.0.2.20"
            );

            overlay.registerEndpoint(
                database.nic("eth0").mac(),
                "192.0.2.30"
            );
        }

        private void registerPolicies() {
            policyEngine.register(
                new NetworkPolicy(
                    "frontend",
                    "frontend",
                    PolicyDecision.ALLOW
                )
            );

            policyEngine.register(
                new NetworkPolicy(
                    "backend",
                    "backend",
                    PolicyDecision.ALLOW
                )
            );

            policyEngine.register(
                new NetworkPolicy(
                    "database",
                    "database",
                    PolicyDecision.ALLOW
                )
            );

            policyEngine.register(
                new NetworkPolicy(
                    "frontend",
                    "backend",
                    PolicyDecision.ALLOW
                )
            );

            policyEngine.register(
                new NetworkPolicy(
                    "backend",
                    "frontend",
                    PolicyDecision.ALLOW
                )
            );

            policyEngine.register(
                new NetworkPolicy(
                    "backend",
                    "database",
                    PolicyDecision.ALLOW
                )
            );

            policyEngine.register(
                new NetworkPolicy(
                    "database",
                    "backend",
                    PolicyDecision.ALLOW
                )
            );

            policyEngine.register(
                new NetworkPolicy(
                    "frontend",
                    "database",
                    PolicyDecision.DENY
                )
            );

            policyEngine.register(
                new NetworkPolicy(
                    "database",
                    "frontend",
                    PolicyDecision.DENY
                )
            );
        }

        void demonstrateSwitching() {
            System.out.println(
                "\n=== Virtual switch forwarding ==="
            );

            VirtualNic web =
                machines.get("web-01").nic("eth0");

            VirtualNic app =
                machines.get("app-01").nic("eth0");

            EthernetFrame request =
                new EthernetFrame(
                    web.mac(),
                    app.mac(),
                    web.address(),
                    app.address(),
                    "GET /orders",
                    110,
                    64
                );

            List<String> first =
                virtualSwitch.forward(
                    request,
                    "web-port"
                );

            System.out.println(
                "Unknown destination outputs: " +
                first
            );

            EthernetFrame response =
                new EthernetFrame(
                    app.mac(),
                    web.mac(),
                    app.address(),
                    web.address(),
                    "HTTP 200",
                    110,
                    64
                );

            List<String> second =
                virtualSwitch.forward(
                    response,
                    "app-port"
                );

            System.out.println(
                "Learned destination outputs: " +
                second
            );

            System.out.println(
                "MAC table: " +
                virtualSwitch.macTable()
            );
        }

        void demonstrateRouting() {
            System.out.println(
                "\n=== Layer-3 virtual routing ==="
            );

            VirtualNic web =
                machines.get("web-01").nic("eth0");

            VirtualNic app =
                machines.get("app-01").nic("eth0");

            EthernetFrame request =
                new EthernetFrame(
                    web.mac(),
                    app.mac(),
                    web.address(),
                    app.address(),
                    "internal service request",
                    110,
                    64
                );

            try {
                EthernetFrame routed =
                    router.route(
                        request,
                        "frontend"
                    );

                System.out.println(
                    "Allowed. New TTL: " +
                    routed.ttl()
                );
            } catch (RuntimeException exception) {
                System.out.println(
                    "Routing failed: " +
                    exception.getMessage()
                );
            }
        }

        void demonstrateOverlay() {
            System.out.println(
                "\n=== VXLAN-style overlay ==="
            );

            VirtualNic web =
                machines.get("web-01").nic("eth0");

            VirtualNic app =
                machines.get("app-01").nic("eth0");

            EthernetFrame inner =
                new EthernetFrame(
                    web.mac(),
                    app.mac(),
                    web.address(),
                    app.address(),
                    "tenant payload",
                    null,
                    64
                );

            OverlayPacket encapsulated =
                overlay.encapsulate(
                    inner,
                    "192.0.2.10",
                    "192.0.2.20",
                    5001
                );

            System.out.println(
                "Outer tunnel: " +
                encapsulated.outerSource() +
                " -> " +
                encapsulated.outerDestination()
            );

            System.out.println(
                "VNI: " +
                encapsulated.vni()
            );

            EthernetFrame recovered =
                overlay.decapsulate(
                    encapsulated,
                    5001
                );

            System.out.println(
                "Recovered destination: " +
                recovered.destinationIp().value()
            );
        }

        void demonstratePolicyViolation() {
            System.out.println(
                "\n=== Network isolation policy ==="
            );

            VirtualNic web =
                machines.get("web-01").nic("eth0");

            VirtualNic database =
                machines.get("db-01").nic("eth0");

            EthernetFrame request =
                new EthernetFrame(
                    web.mac(),
                    database.mac(),
                    web.address(),
                    database.address(),
                    "direct database connection",
                    110,
                    64
                );

            try {
                router.route(
                    request,
                    "frontend"
                );

                System.out.println(
                    "Unexpected policy success"
                );
            } catch (SecurityException exception) {
                System.out.println(
                    "Expected security decision: " +
                    exception.getMessage()
                );
            }
        }

        void demonstrateFailure() {
            System.out.println(
                "\n=== Virtual network failure ==="
            );

            virtualSwitch.setPortState(
                "app-port",
                PortState.DOWN
            );

            VirtualNic web =
                machines.get("web-01").nic("eth0");

            VirtualNic app =
                machines.get("app-01").nic("eth0");

            EthernetFrame request =
                new EthernetFrame(
                    web.mac(),
                    app.mac(),
                    web.address(),
                    app.address(),
                    "traffic during outage",
                    110,
                    64
                );

            List<String> result =
                virtualSwitch.forward(
                    request,
                    "web-port"
                );

            System.out.println(
                "Forwarding during port failure: " +
                result
            );

            virtualSwitch.setPortState(
                "app-port",
                PortState.UP
            );

            System.out.println(
                "Port restored."
            );
        }

        void printTopology() {
            System.out.println(
                "=== Enterprise virtual network ==="
            );

            networks.values()
                .forEach(
                    network ->
                        System.out.printf(
                            "%s subnet=%s VLAN=%d VNI=%d gateway=%s isolated=%s%n",
                            network.name(),
                            network.subnet().network() +
                                "/" +
                                network.subnet().prefixLength(),
                            network.vlanId(),
                            network.vni(),
                            network.gateway().value(),
                            network.isolated()
                        )
                );

            machines.values()
                .forEach(
                    machine ->
                        machine.nics().values()
                            .forEach(
                                nic ->
                                    System.out.printf(
                                        "%s/%s MAC=%s IP=%s network=%s%n",
                                        machine.name(),
                                        nic.name(),
                                        nic.mac().value(),
                                        nic.address().value(),
                                        nic.networkName()
                                    )
                            )
                );
        }

        void run() {
            printTopology();
            demonstrateSwitching();
            demonstrateRouting();
            demonstrateOverlay();
            demonstratePolicyViolation();
            demonstrateFailure();

            System.out.println(
                "\n=== Operational counters ==="
            );

            virtualSwitch.printStatistics();
        }
    }

    public static void main(String[] args) {
        try {
            RepositoryNetworkService service =
                new RepositoryNetworkService();

            service.initialize();
            service.run();
        } catch (RuntimeException exception) {
            System.err.println(
                "Network virtualization failure: " +
                exception.getMessage()
            );
            System.exit(1);
        }
    }
}
