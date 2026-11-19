import java.net.Inet4Address;
import java.net.UnknownHostException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.UUID;

/*
 * Docker Networking: Enterprise Network Governance Simulator
 *
 * Java 17
 *
 * Implements:
 * - Network domain objects
 * - Bridge and host networking
 * - Custom network subnets
 * - Container lifecycle
 * - DNS aliases
 * - Port publishing
 * - Network attachment and detachment
 * - Communication authorization
 * - Network policy evaluation
 * - Audit events
 * - Validation and failure handling
 */

public class DockerNetworkingEnterprise {

    enum NetworkDriver {
        BRIDGE,
        HOST
    }

    enum ContainerStatus {
        RUNNING,
        STOPPED
    }

    enum Protocol {
        TCP,
        UDP
    }

    static class NetworkException extends RuntimeException {
        NetworkException(String message) {
            super(message);
        }
    }

    static class ValidationException extends NetworkException {
        ValidationException(String message) {
            super(message);
        }
    }

    static class AddressConflictException extends NetworkException {
        AddressConflictException(String message) {
            super(message);
        }
    }

    record ResourceAddress(String address, int prefix) {
        ResourceAddress {
            if (prefix < 16 || prefix > 30) {
                throw new ValidationException("Unsupported prefix.");
            }

            parseIPv4(address);
        }

        long numericAddress() {
            return toLong(parseIPv4(address));
        }

        long mask() {
            return (0xFFFFFFFFL << (32 - prefix)) & 0xFFFFFFFFL;
        }

        long network() {
            return numericAddress() & mask();
        }

        long broadcast() {
            return network() | (~mask() & 0xFFFFFFFFL);
        }

        boolean contains(String candidate) {
            long value = toLong(parseIPv4(candidate));
            return (value & mask()) == network();
        }

        boolean overlaps(ResourceAddress other) {
            return (network() & other.mask()) == other.network()
                    || (other.network() & mask()) == network();
        }
    }

    record PortMapping(
            int containerPort,
            int hostPort,
            Protocol protocol
    ) {
        PortMapping {
            if (
                    containerPort < 1 || containerPort > 65535
                    || hostPort < 1 || hostPort > 65535
            ) {
                throw new ValidationException("Invalid port mapping.");
            }

            Objects.requireNonNull(protocol);
        }
    }

    static class Container {
        private final String name;
        private final String image;
        private final Set<Integer> exposedPorts;
        private final Set<String> networks = new HashSet<>();
        private ContainerStatus status = ContainerStatus.RUNNING;

        Container(
                String name,
                String image,
                Set<Integer> exposedPorts
        ) {
            if (
                    name == null || name.isBlank()
                    || image == null || image.isBlank()
            ) {
                throw new ValidationException(
                        "Container name and image are required."
                );
            }

            for (int port : exposedPorts) {
                if (port < 1 || port > 65535) {
                    throw new ValidationException("Invalid exposed port.");
                }
            }

            this.name = name;
            this.image = image;
            this.exposedPorts = Set.copyOf(exposedPorts);
        }

        String name() {
            return name;
        }

        String image() {
            return image;
        }

        ContainerStatus status() {
            return status;
        }

        Set<String> networks() {
            return Collections.unmodifiableSet(networks);
        }

        boolean exposes(int port) {
            return exposedPorts.contains(port);
        }
    }

    static class DockerNetwork {
        private final String name;
        private final NetworkDriver driver;
        private final ResourceAddress subnet;
        private final String gateway;
        private final Map<String, String> addresses = new TreeMap<>();
        private final Map<String, String> dnsAliases = new HashMap<>();
        private long nextAddress;

        DockerNetwork(
                String name,
                NetworkDriver driver,
                ResourceAddress subnet
        ) {
            this.name = name;
            this.driver = driver;
            this.subnet = subnet;

            if (driver == NetworkDriver.BRIDGE) {
                if (subnet == null) {
                    throw new ValidationException(
                            "Bridge requires a subnet."
                    );
                }

                gateway = formatIPv4(subnet.network() + 1);
                nextAddress = subnet.network() + 2;
            } else {
                if (subnet != null) {
                    throw new ValidationException(
                            "Host network cannot have an isolated subnet."
                    );
                }

                gateway = null;
            }
        }

        String allocateAddress() {
            if (driver != NetworkDriver.BRIDGE) {
                throw new NetworkException(
                        "Host networking does not allocate bridge addresses."
                );
            }

            while (nextAddress < subnet.broadcast()) {
                String candidate = formatIPv4(nextAddress++);

                if (!candidate.equals(gateway)
                        && !addresses.containsValue(candidate)) {
                    return candidate;
                }
            }

            throw new AddressConflictException(
                    "Network address pool exhausted."
            );
        }

        String name() {
            return name;
        }

        NetworkDriver driver() {
            return driver;
        }
    }

    record AuditEvent(
            String action,
            String subject,
            String detail
    ) {}

    static class NetworkPolicy {
        private final Set<String> allowedSourceNetworks;
        private final Set<Integer> allowedDestinationPorts;

        NetworkPolicy(
                Set<String> allowedSourceNetworks,
                Set<Integer> allowedDestinationPorts
        ) {
            this.allowedSourceNetworks = Set.copyOf(
                    allowedSourceNetworks
            );
            this.allowedDestinationPorts = Set.copyOf(
                    allowedDestinationPorts
            );
        }

        boolean permits(
                Container source,
                Container destination,
                int destinationPort
        ) {
            boolean sharedAllowedNetwork =
                    source.networks().stream()
                            .anyMatch(allowedSourceNetworks::contains);

            return sharedAllowedNetwork
                    && allowedDestinationPorts.contains(destinationPort)
                    && destination.exposes(destinationPort);
        }
    }

    static class NetworkService {
        private final Map<String, Container> containers =
                new TreeMap<>();

        private final Map<String, DockerNetwork> networks =
                new TreeMap<>();

        private final Map<String, String> publishedPorts =
                new HashMap<>();

        private final List<AuditEvent> auditLog =
                new ArrayList<>();

        private void audit(
                String action,
                String subject,
                String detail
        ) {
            auditLog.add(new AuditEvent(action, subject, detail));
        }

        void createNetwork(
                String name,
                NetworkDriver driver,
                ResourceAddress subnet
        ) {
            if (networks.containsKey(name)) {
                throw new ValidationException("Duplicate network.");
            }

            if (driver == NetworkDriver.BRIDGE) {
                for (DockerNetwork existing : networks.values()) {
                    if (
                            existing.subnet != null
                            && existing.subnet.overlaps(subnet)
                    ) {
                        throw new AddressConflictException(
                                "Network subnet overlaps " + existing.name
                        );
                    }
                }
            }

            networks.put(
                    name,
                    new DockerNetwork(name, driver, subnet)
            );

            audit("NETWORK_CREATED", name, driver.name());
        }

        void createContainer(
                String name,
                String image,
                Set<Integer> ports
        ) {
            if (containers.containsKey(name)) {
                throw new ValidationException(
                        "Container already exists."
                );
            }

            containers.put(
                    name,
                    new Container(name, image, ports)
            );

            audit("CONTAINER_CREATED", name, image);
        }

        void connect(
                String containerName,
                String networkName,
                Set<String> aliases
        ) {
            Container container = requiredContainer(containerName);
            DockerNetwork network = requiredNetwork(networkName);

            if (container.status != ContainerStatus.RUNNING) {
                throw new NetworkException("Container is stopped.");
            }

            if (container.networks.contains(networkName)) {
                throw new ValidationException(
                        "Container already connected."
                );
            }

            for (String alias : aliases) {
                String owner = network.dnsAliases.get(alias);

                if (alias == null || alias.isBlank()) {
                    throw new ValidationException("Invalid DNS alias.");
                }

                if (owner != null && !owner.equals(containerName)) {
                    throw new ValidationException(
                            "DNS alias already belongs to another container."
                    );
                }
            }

            if (network.driver == NetworkDriver.BRIDGE) {
                String address = network.allocateAddress();

                network.addresses.put(containerName, address);
                network.dnsAliases.put(containerName, containerName);

                for (String alias : aliases) {
                    network.dnsAliases.put(alias, containerName);
                }
            }

            container.networks.add(networkName);

            audit(
                    "CONTAINER_CONNECTED",
                    containerName,
                    networkName
            );
        }

        void disconnect(
                String containerName,
                String networkName
        ) {
            Container container = requiredContainer(containerName);
            DockerNetwork network = requiredNetwork(networkName);

            if (network.driver == NetworkDriver.HOST) {
                throw new NetworkException(
                        "Host network cannot be detached independently."
                );
            }

            if (!container.networks.remove(networkName)) {
                throw new ValidationException(
                        "Container is not connected."
                );
            }

            network.addresses.remove(containerName);

            network.dnsAliases.entrySet().removeIf(
                    entry -> entry.getValue().equals(containerName)
            );

            audit(
                    "CONTAINER_DISCONNECTED",
                    containerName,
                    networkName
            );
        }

        String resolve(
                String sourceName,
                String alias,
                String networkName
        ) {
            Container source = requiredContainer(sourceName);
            DockerNetwork network = requiredNetwork(networkName);

            if (network.driver != NetworkDriver.BRIDGE) {
                throw new NetworkException(
                        "Bridge DNS is not available for host networking."
                );
            }

            if (!source.networks.contains(networkName)) {
                throw new NetworkException(
                        "Source is not attached to network."
                );
            }

            String destination =
                    network.dnsAliases.get(alias);

            if (destination == null) {
                throw new NetworkException(
                        "DNS record does not exist."
                );
            }

            return network.addresses.get(destination);
        }

        void publish(
                String containerName,
                PortMapping mapping
        ) {
            Container container = requiredContainer(containerName);

            if (!container.exposes(mapping.containerPort())) {
                throw new ValidationException(
                        "Container port is not exposed."
                );
            }

            String key = mapping.hostPort()
                    + "/" + mapping.protocol();

            if (publishedPorts.containsKey(key)) {
                throw new AddressConflictException(
                        "Host port is already allocated."
                );
            }

            publishedPorts.put(key, containerName);

            audit(
                    "PORT_PUBLISHED",
                    containerName,
                    key
            );
        }

        boolean communicate(
                String sourceName,
                String destinationName,
                String networkName,
                int port,
                NetworkPolicy policy
        ) {
            Container source = requiredContainer(sourceName);
            Container destination = requiredContainer(destinationName);
            DockerNetwork network = requiredNetwork(networkName);

            if (
                    source.status != ContainerStatus.RUNNING
                    || destination.status != ContainerStatus.RUNNING
            ) {
                return false;
            }

            if (
                    !source.networks.contains(networkName)
                    || !destination.networks.contains(networkName)
                    || !destination.exposes(port)
            ) {
                return false;
            }

            return policy == null
                    || policy.permits(source, destination, port);
        }

        void stop(String containerName) {
            Container container = requiredContainer(containerName);
            container.status = ContainerStatus.STOPPED;

            publishedPorts.entrySet().removeIf(
                    entry -> entry.getValue().equals(containerName)
            );

            audit("CONTAINER_STOPPED", containerName, "Stopped");
        }

        private Container requiredContainer(String name) {
            Container container = containers.get(name);

            if (container == null) {
                throw new ValidationException(
                        "Unknown container: " + name
                );
            }

            return container;
        }

        private DockerNetwork requiredNetwork(String name) {
            DockerNetwork network = networks.get(name);

            if (network == null) {
                throw new ValidationException(
                        "Unknown network: " + name
                );
            }

            return network;
        }

        void report() {
            System.out.println("\nNETWORK INVENTORY");

            for (DockerNetwork network : networks.values()) {
                System.out.println(
                        network.name + " [" + network.driver + "]"
                );

                if (network.subnet != null) {
                    System.out.println(
                            "  Gateway: " + network.gateway
                    );
                }

                network.addresses.forEach(
                        (container, address) ->
                                System.out.println(
                                        "  " + container + ": " + address
                                )
                );
            }

            System.out.println("\nPUBLISHED PORTS");
            publishedPorts.forEach(
                    (port, container) ->
                            System.out.println(
                                    port + " -> " + container
                            )
            );

            System.out.println("\nAUDIT EVENTS");
            auditLog.forEach(System.out::println);
        }
    }

    static byte[] parseIPv4(String address) {
        try {
            byte[] bytes = Inet4Address.getByName(address).getAddress();

            if (bytes.length != 4 || !formatIPv4(toLong(bytes)).equals(address)) {
                throw new ValidationException("Invalid IPv4 address.");
            }

            return bytes;
        } catch (UnknownHostException exception) {
            throw new ValidationException("Invalid IPv4 address.");
        }
    }

    static long toLong(byte[] bytes) {
        return ((long) (bytes[0] & 255) << 24)
                | ((long) (bytes[1] & 255) << 16)
                | ((long) (bytes[2] & 255) << 8)
                | (long) (bytes[3] & 255);
    }

    static String formatIPv4(long value) {
        return ((value >>> 24) & 255) + "."
                + ((value >>> 16) & 255) + "."
                + ((value >>> 8) & 255) + "."
                + (value & 255);
    }

    public static void main(String[] args) {
        NetworkService service = new NetworkService();

        try {
            service.createNetwork(
                    "frontend",
                    NetworkDriver.BRIDGE,
                    new ResourceAddress("172.20.0.0", 24)
            );

            service.createNetwork(
                    "backend",
                    NetworkDriver.BRIDGE,
                    new ResourceAddress("172.21.0.0", 24)
            );

            service.createNetwork(
                    "host-network",
                    NetworkDriver.HOST,
                    null
            );

            service.createContainer(
                    "web",
                    "nginx:1.27",
                    Set.of(80)
            );

            service.createContainer(
                    "api",
                    "python:3.13",
                    Set.of(8000)
            );

            service.createContainer(
                    "database",
                    "postgres:18",
                    Set.of(5432)
            );

            service.connect("web", "frontend", Set.of());
            service.connect("api", "frontend", Set.of("api-service"));
            service.connect("api", "backend", Set.of());
            service.connect("database", "backend", Set.of("db"));

            service.connect("web", "host-network", Set.of());

            String apiAddress = service.resolve(
                    "web",
                    "api-service",
                    "frontend"
            );

            System.out.println("API address: " + apiAddress);

            NetworkPolicy frontendPolicy = new NetworkPolicy(
                    Set.of("frontend"),
                    Set.of(8000)
            );

            if (!service.communicate(
                    "web",
                    "api",
                    "frontend",
                    8000,
                    frontendPolicy
            )) {
                throw new NetworkException(
                        "Expected frontend communication."
                );
            }

            if (service.communicate(
                    "web",
                    "database",
                    "frontend",
                    5432,
                    null
            )) {
                throw new NetworkException(
                        "Network isolation failure."
                );
            }

            service.publish(
                    "web",
                    new PortMapping(80, 8080, Protocol.TCP)
            );

            // Stopped containers must lose their published bindings.
            service.stop("web");

            service.report();

            // Overlapping subnet must fail.
            try {
                service.createNetwork(
                        "conflict",
                        NetworkDriver.BRIDGE,
                        new ResourceAddress("172.20.0.0", 25)
                );

                throw new NetworkException(
                        "Subnet overlap was accepted."
                );
            } catch (AddressConflictException expected) {
                System.out.println(
                        "Overlapping subnet rejected correctly."
                );
            }

            System.out.println(
                    "\nAll enterprise network tests passed."
            );

        } catch (NetworkException exception) {
            System.err.println(
                    "Network operation failed: " + exception.getMessage()
            );
            System.exit(1);
        }
    }
}
