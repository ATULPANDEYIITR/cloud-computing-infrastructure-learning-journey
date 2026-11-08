import java.util.*;
import java.util.stream.Collectors;

/**
 * Cloud Network Security Governance Engine
 *
 * Enterprise-oriented implementation of:
 * - Stateful security groups
 * - Stateless network ACLs
 * - Ordered perimeter firewalls
 * - IPv4 CIDR matching
 * - Connection tracking
 * - Policy validation
 * - Merge-independent network security decisions
 *
 * Java 17, standard library only.
 *
 * Compile: javac CloudNetworkSecurity.java
 * Run:     java CloudNetworkSecurity
 */
public class CloudNetworkSecurity {

    enum Direction {
        INBOUND, OUTBOUND
    }

    enum Action {
        ALLOW, DENY
    }

    enum Protocol {
        TCP, UDP, ICMP, ALL
    }

    enum Decision {
        ALLOW, DENY
    }

    static class SecurityException extends RuntimeException {
        SecurityException(String message) {
            super(message);
        }
    }

    record IPv4(long value) {

        static IPv4 parse(String address) {
            String[] parts = address.split("\\.", -1);

            if (parts.length != 4) {
                throw new SecurityException("Invalid IPv4 address");
            }

            long value = 0;

            for (String part : parts) {
                try {
                    if (
                        part.isEmpty() ||
                        part.length() > 3 ||
                        !part.matches("\\d+")
                    ) {
                        throw new NumberFormatException();
                    }

                    int octet = Integer.parseInt(part);

                    if (octet < 0 || octet > 255) {
                        throw new NumberFormatException();
                    }

                    value = (value << 8) | octet;

                } catch (NumberFormatException exception) {
                    throw new SecurityException(
                        "Invalid IPv4 octet: " + part
                    );
                }
            }

            return new IPv4(value);
        }
    }

    record CIDR(long network, long mask) {

        static CIDR parse(String value) {
            String[] parts = value.split("/", -1);

            if (parts.length != 2) {
                throw new SecurityException("Invalid CIDR");
            }

            IPv4 ip = IPv4.parse(parts[0]);

            int prefix;

            try {
                prefix = Integer.parseInt(parts[1]);
            } catch (NumberFormatException exception) {
                throw new SecurityException("Invalid CIDR prefix");
            }

            if (prefix < 0 || prefix > 32) {
                throw new SecurityException("CIDR prefix must be 0-32");
            }

            long mask = prefix == 0
                ? 0L
                : (0xFFFFFFFFL << (32 - prefix)) & 0xFFFFFFFFL;

            return new CIDR(ip.value() & mask, mask);
        }

        boolean contains(String address) {
            long ip = IPv4.parse(address).value();
            return (ip & mask) == network;
        }
    }

    record Packet(
        String sourceIP,
        String destinationIP,
        Protocol protocol,
        int sourcePort,
        int destinationPort
    ) {
        Packet {
            Objects.requireNonNull(sourceIP);
            Objects.requireNonNull(destinationIP);
            Objects.requireNonNull(protocol);

            IPv4.parse(sourceIP);
            IPv4.parse(destinationIP);

            validatePort(sourcePort);
            validatePort(destinationPort);

            if (
                (protocol == Protocol.ICMP || protocol == Protocol.ALL) &&
                (sourcePort != 0 || destinationPort != 0)
            ) {
                throw new SecurityException(
                    "ICMP and ALL packets must use zero ports"
                );
            }
        }

        private static void validatePort(int port) {
            if (port < 0 || port > 65535) {
                throw new SecurityException("Invalid packet port");
            }
        }
    }

    record Rule(
        String id,
        Direction direction,
        Action action,
        Protocol protocol,
        CIDR cidr,
        int portStart,
        int portEnd,
        int priority,
        String description
    ) {

        Rule {
            if (id == null || id.isBlank()) {
                throw new SecurityException("Rule ID is required");
            }

            Objects.requireNonNull(direction);
            Objects.requireNonNull(action);
            Objects.requireNonNull(protocol);
            Objects.requireNonNull(cidr);

            if (
                portStart < 0 ||
                portEnd > 65535 ||
                portStart > portEnd
            ) {
                throw new SecurityException("Invalid rule port range");
            }

            if (priority < 0) {
                throw new SecurityException("Invalid priority");
            }

            if (
                (protocol == Protocol.ICMP || protocol == Protocol.ALL) &&
                (portStart != 0 || portEnd != 65535)
            ) {
                throw new SecurityException(
                    "ICMP and ALL rules must use the full port range"
                );
            }
        }

        boolean matches(Packet packet, Direction requestedDirection) {
            if (direction != requestedDirection) {
                return false;
            }

            String address = direction == Direction.INBOUND
                ? packet.sourceIP()
                : packet.destinationIP();

            if (!cidr.contains(address)) {
                return false;
            }

            if (
                protocol != Protocol.ALL &&
                protocol != packet.protocol()
            ) {
                return false;
            }

            if (
                packet.protocol() == Protocol.ICMP ||
                packet.protocol() == Protocol.ALL
            ) {
                return true;
            }

            return packet.destinationPort() >= portStart &&
                   packet.destinationPort() <= portEnd;
        }
    }

    record ConnectionKey(
        String sourceIP,
        String destinationIP,
        Protocol protocol,
        int sourcePort,
        int destinationPort
    ) {

        static ConnectionKey forward(Packet packet) {
            return new ConnectionKey(
                packet.sourceIP(),
                packet.destinationIP(),
                packet.protocol(),
                packet.sourcePort(),
                packet.destinationPort()
            );
        }

        static ConnectionKey reverse(Packet packet) {
            return new ConnectionKey(
                packet.destinationIP(),
                packet.sourceIP(),
                packet.protocol(),
                packet.destinationPort(),
                packet.sourcePort()
            );
        }
    }

    static class ConnectionTracker {
        private final Map<ConnectionKey, Long> connections =
            new HashMap<>();

        private final long ttlMillis;

        ConnectionTracker(long ttlMillis) {
            if (ttlMillis <= 0) {
                throw new SecurityException("Invalid connection TTL");
            }

            this.ttlMillis = ttlMillis;
        }

        synchronized boolean contains(Packet packet) {
            cleanup();

            return connections.containsKey(
                ConnectionKey.forward(packet)
            ) || connections.containsKey(
                ConnectionKey.reverse(packet)
            );
        }

        synchronized void add(Packet packet) {
            connections.put(
                ConnectionKey.forward(packet),
                System.currentTimeMillis() + ttlMillis
            );
        }

        synchronized void cleanup() {
            long now = System.currentTimeMillis();

            connections.entrySet().removeIf(
                entry -> entry.getValue() <= now
            );
        }

        synchronized int size() {
            cleanup();
            return connections.size();
        }
    }

    record Evaluation(
        Decision decision,
        String layer,
        String reason,
        String ruleId
    ) {}

    interface PolicyLayer {
        Evaluation inspect(Packet packet, Direction direction);

        String name();

        int ruleCount();
    }

    static abstract class AbstractPolicyLayer
        implements PolicyLayer {

        protected final String name;
        protected final Map<String, Rule> rules =
            new LinkedHashMap<>();

        AbstractPolicyLayer(String name) {
            if (name == null || name.isBlank()) {
                throw new SecurityException("Layer name is required");
            }

            this.name = name;
        }

        @Override
        public String name() {
            return name;
        }

        @Override
        public int ruleCount() {
            return rules.size();
        }

        protected void addRule(Rule rule) {
            if (rules.containsKey(rule.id())) {
                throw new SecurityException(
                    "Duplicate rule ID: " + rule.id()
                );
            }

            rules.put(rule.id(), rule);
        }

        protected List<Rule> orderedRules() {
            return rules.values()
                .stream()
                .sorted(
                    Comparator.comparingInt(Rule::priority)
                )
                .toList();
        }

        protected Evaluation evaluateRules(
            Packet packet,
            Direction direction
        ) {
            for (Rule rule : orderedRules()) {
                if (rule.matches(packet, direction)) {
                    return new Evaluation(
                        rule.action() == Action.ALLOW
                            ? Decision.ALLOW
                            : Decision.DENY,
                        name,
                        "Matched policy rule",
                        rule.id()
                    );
                }
            }

            return new Evaluation(
                Decision.DENY,
                name,
                "Default deny",
                null
            );
        }
    }

    static final class SecurityGroup
        extends AbstractPolicyLayer {

        private final ConnectionTracker tracker =
            new ConnectionTracker(300_000);

        SecurityGroup(String name) {
            super(name);
        }

        void register(Rule rule) {
            if (rule.action() != Action.ALLOW) {
                throw new SecurityException(
                    "Security groups support ALLOW rules only"
                );
            }

            addRule(rule);
        }

        @Override
        public Evaluation inspect(
            Packet packet,
            Direction direction
        ) {
            if (tracker.contains(packet)) {
                return new Evaluation(
                    Decision.ALLOW,
                    name,
                    "Established connection",
                    null
                );
            }

            Evaluation result = evaluateRules(packet, direction);

            if (
                result.decision() == Decision.ALLOW &&
                direction == Direction.OUTBOUND
            ) {
                tracker.add(packet);
            }

            return result;
        }

        int trackedConnections() {
            return tracker.size();
        }
    }

    static final class NetworkACL
        extends AbstractPolicyLayer {

        NetworkACL(String name) {
            super(name);
        }

        void register(Rule rule) {
            addRule(rule);
        }

        @Override
        public Evaluation inspect(
            Packet packet,
            Direction direction
        ) {
            // No connection tracking: response rules are explicit.
            return evaluateRules(packet, direction);
        }
    }

    static final class Firewall
        extends AbstractPolicyLayer {

        private final ConnectionTracker tracker =
            new ConnectionTracker(300_000);

        Firewall(String name) {
            super(name);
        }

        void register(Rule rule) {
            addRule(rule);
        }

        @Override
        public Evaluation inspect(
            Packet packet,
            Direction direction
        ) {
            if (tracker.contains(packet)) {
                return new Evaluation(
                    Decision.ALLOW,
                    name,
                    "Established firewall connection",
                    null
                );
            }

            Evaluation result = evaluateRules(packet, direction);

            if (
                result.decision() == Decision.ALLOW &&
                direction == Direction.INBOUND
            ) {
                tracker.add(packet);
            }

            return result;
        }
    }

    static final class NetworkSecurityService {

        private final List<PolicyLayer> layers;

        NetworkSecurityService(
            NetworkACL acl,
            SecurityGroup group,
            Firewall firewall
        ) {
            layers = List.of(acl, group, firewall);
        }

        Evaluation inspect(
            Packet packet,
            Direction direction
        ) {
            Objects.requireNonNull(packet);
            Objects.requireNonNull(direction);

            List<Evaluation> auditTrail = new ArrayList<>();

            for (PolicyLayer layer : layers) {
                Evaluation result = layer.inspect(
                    packet,
                    direction
                );

                auditTrail.add(result);

                System.out.printf(
                    "%s: %s (%s)%n",
                    result.layer(),
                    result.decision(),
                    result.reason()
                );

                if (result.decision() == Decision.DENY) {
                    return result;
                }
            }

            return new Evaluation(
                Decision.ALLOW,
                "network-security-service",
                "All policy layers accepted traffic",
                null
            );
        }

        void audit() {
            System.out.println("\nSECURITY POLICY AUDIT");

            layers.forEach(layer -> System.out.printf(
                "%-24s rules=%d%n",
                layer.name(),
                layer.ruleCount()
            ));
        }
    }

    static Rule rule(
        String id,
        Direction direction,
        Action action,
        Protocol protocol,
        String cidr,
        int start,
        int end,
        int priority
    ) {
        return new Rule(
            id,
            direction,
            action,
            protocol,
            CIDR.parse(cidr),
            start,
            end,
            priority,
            id
        );
    }

    static NetworkSecurityService buildEnterpriseEnvironment() {
        SecurityGroup group = new SecurityGroup(
            "production-application-sg"
        );

        group.register(rule(
            "sg-public-https",
            Direction.INBOUND,
            Action.ALLOW,
            Protocol.TCP,
            "0.0.0.0/0",
            443, 443, 100
        ));

        group.register(rule(
            "sg-private-database",
            Direction.OUTBOUND,
            Action.ALLOW,
            Protocol.TCP,
            "10.0.2.0/24",
            5432, 5432, 100
        ));

        group.register(rule(
            "sg-admin",
            Direction.INBOUND,
            Action.ALLOW,
            Protocol.TCP,
            "10.0.1.0/24",
            22, 22, 110
        ));

        NetworkACL acl = new NetworkACL(
            "production-subnet-acl"
        );

        acl.register(rule(
            "acl-https",
            Direction.INBOUND,
            Action.ALLOW,
            Protocol.TCP,
            "0.0.0.0/0",
            443, 443, 100
        ));

        acl.register(rule(
            "acl-admin",
            Direction.INBOUND,
            Action.ALLOW,
            Protocol.TCP,
            "10.0.1.0/24",
            22, 22, 110
        ));

        acl.register(rule(
            "acl-return",
            Direction.OUTBOUND,
            Action.ALLOW,
            Protocol.TCP,
            "0.0.0.0/0",
            0, 65535, 100
        ));

        Firewall firewall = new Firewall(
            "enterprise-perimeter-firewall"
        );

        firewall.register(rule(
            "fw-deny-hostile-range",
            Direction.INBOUND,
            Action.DENY,
            Protocol.ALL,
            "198.51.100.0/24",
            0, 65535, 10
        ));

        firewall.register(rule(
            "fw-allow-https",
            Direction.INBOUND,
            Action.ALLOW,
            Protocol.TCP,
            "0.0.0.0/0",
            443, 443, 100
        ));

        firewall.register(rule(
            "fw-allow-admin",
            Direction.INBOUND,
            Action.ALLOW,
            Protocol.TCP,
            "10.0.1.0/24",
            22, 22, 110
        ));

        firewall.register(rule(
            "fw-outbound",
            Direction.OUTBOUND,
            Action.ALLOW,
            Protocol.ALL,
            "0.0.0.0/0",
            0, 65535, 100
        ));

        return new NetworkSecurityService(
            acl,
            group,
            firewall
        );
    }

    public static void main(String[] args) {
        try {
            NetworkSecurityService service =
                buildEnterpriseEnvironment();

            System.out.println(
                "ENTERPRISE CLOUD NETWORK SECURITY"
            );
            System.out.println("=================================");

            Packet publicHttps = new Packet(
                "203.0.113.10",
                "10.0.0.10",
                Protocol.TCP,
                51000,
                443
            );

            Packet hostileHttps = new Packet(
                "198.51.100.20",
                "10.0.0.10",
                Protocol.TCP,
                51000,
                443
            );

            Packet unauthorizedSSH = new Packet(
                "203.0.113.20",
                "10.0.0.10",
                Protocol.TCP,
                51000,
                22
            );

            Evaluation first = service.inspect(
                publicHttps,
                Direction.INBOUND
            );

            if (first.decision() != Decision.ALLOW) {
                throw new SecurityException(
                    "Public HTTPS validation failed"
                );
            }

            System.out.println(
                "\nHTTPS: " + first.decision()
            );

            Evaluation second = service.inspect(
                hostileHttps,
                Direction.INBOUND
            );

            if (second.decision() != Decision.DENY) {
                throw new SecurityException(
                    "Hostile network should be denied"
                );
            }

            System.out.println(
                "\nHostile source: " + second.decision()
            );

            Evaluation third = service.inspect(
                unauthorizedSSH,
                Direction.INBOUND
            );

            if (third.decision() != Decision.DENY) {
                throw new SecurityException(
                    "Unauthorized SSH should be denied"
                );
            }

            System.out.println(
                "\nUnauthorized SSH: " + third.decision()
            );

            service.audit();

            System.out.println(
                "\nAll enterprise security tests passed."
            );

        } catch (SecurityException exception) {
            System.err.println(
                "Security policy failure: " + exception.getMessage()
            );
            System.exit(1);
        }
    }
}
