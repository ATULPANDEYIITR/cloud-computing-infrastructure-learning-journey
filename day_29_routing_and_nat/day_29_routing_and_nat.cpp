/*
 * Routing and NAT: Industry-Style Network Gateway Case Study
 *
 * Standard: C++17 or later
 *
 * This program models a small enterprise network containing:
 *
 *   Client LAN
 *       |
 *       | 192.168.50.0/24
 *       |
 *   Edge Router / NAT Gateway
 *       |
 *       | 203.0.113.0/30
 *       |
 *   ISP Router
 *       |
 *       | 198.51.100.0/24
 *       |
 *   Internet Server
 *
 * The implementation demonstrates:
 *   - IPv4 representation
 *   - CIDR networks
 *   - routing tables
 *   - longest-prefix matching
 *   - route metrics
 *   - default gateways
 *   - router forwarding
 *   - TTL
 *   - NAT/PAT
 *   - reverse NAT
 *   - traceroute concepts
 *   - failure conditions
 *   - complexity considerations
 *   - structured diagnostics
 *
 * The program is a simulation. It does not alter the operating system's
 * routing table or network configuration.
 */

#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <exception>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <utility>
#include <vector>

using IPv4 = std::uint32_t;

// ============================================================================
// 1. IPv4 UTILITIES
// ============================================================================

IPv4 parseIPv4(const std::string& text) {
    std::stringstream stream(text);
    std::string part;
    std::vector<unsigned int> octets;

    while (std::getline(stream, part, '.')) {
        if (part.empty()) {
            throw std::invalid_argument("Invalid IPv4 address: " + text);
        }

        unsigned long value = 0;

        try {
            value = std::stoul(part);
        } catch (...) {
            throw std::invalid_argument("Invalid IPv4 octet: " + part);
        }

        if (value > 255) {
            throw std::invalid_argument("IPv4 octet out of range: " + part);
        }

        octets.push_back(static_cast<unsigned int>(value));
    }

    if (octets.size() != 4) {
        throw std::invalid_argument("IPv4 address requires four octets: " + text);
    }

    return
        (static_cast<IPv4>(octets[0]) << 24) |
        (static_cast<IPv4>(octets[1]) << 16) |
        (static_cast<IPv4>(octets[2]) << 8) |
        static_cast<IPv4>(octets[3]);
}

std::string ipv4ToString(IPv4 address) {
    std::ostringstream output;

    output
        << ((address >> 24) & 0xFF) << "."
        << ((address >> 16) & 0xFF) << "."
        << ((address >> 8) & 0xFF) << "."
        << (address & 0xFF);

    return output.str();
}

IPv4 prefixMask(unsigned int prefixLength) {
    if (prefixLength > 32) {
        throw std::invalid_argument("Prefix length must be 0..32");
    }

    if (prefixLength == 0) {
        return 0;
    }

    return static_cast<IPv4>(0xFFFFFFFFu << (32 - prefixLength));
}

struct Network {
    IPv4 networkAddress;
    unsigned int prefixLength;

    Network(IPv4 address, unsigned int prefix)
        : networkAddress(address & prefixMask(prefix)),
          prefixLength(prefix) {}

    explicit Network(const std::string& cidr) {
        const auto slash = cidr.find('/');

        if (slash == std::string::npos) {
            throw std::invalid_argument("Invalid CIDR: " + cidr);
        }

        const std::string addressPart = cidr.substr(0, slash);
        const std::string prefixPart = cidr.substr(slash + 1);

        const unsigned long prefix = std::stoul(prefixPart);

        if (prefix > 32) {
            throw std::invalid_argument("Invalid CIDR prefix: " + cidr);
        }

        prefixLength = static_cast<unsigned int>(prefix);
        networkAddress =
            parseIPv4(addressPart) & prefixMask(prefixLength);
    }

    bool contains(IPv4 address) const {
        return (address & prefixMask(prefixLength)) == networkAddress;
    }

    std::string toString() const {
        return ipv4ToString(networkAddress) +
               "/" +
               std::to_string(prefixLength);
    }
};

// ============================================================================
// 2. PACKET MODEL
// ============================================================================

struct Packet {
    IPv4 sourceIP;
    IPv4 destinationIP;

    std::optional<std::uint16_t> sourcePort;
    std::optional<std::uint16_t> destinationPort;

    std::string protocol;
    int ttl;
    std::string payload;

    std::string summary() const {
        std::ostringstream output;

        output
            << protocol << " "
            << ipv4ToString(sourceIP);

        if (sourcePort.has_value()) {
            output << ":" << *sourcePort;
        }

        output << " -> "
               << ipv4ToString(destinationIP);

        if (destinationPort.has_value()) {
            output << ":" << *destinationPort;
        }

        output << " TTL=" << ttl;

        return output.str();
    }
};

// ============================================================================
// 3. ROUTING TABLE
// ============================================================================

struct Route {
    Network network;
    std::optional<IPv4> nextHop;
    std::string interfaceName;
    int metric;
    std::string description;

    Route(
        const std::string& cidr,
        std::optional<std::string> nextHopAddress,
        std::string interfaceName,
        int metric,
        std::string description
    )
        : network(cidr),
          interfaceName(std::move(interfaceName)),
          metric(metric),
          description(std::move(description)) {

        if (nextHopAddress.has_value()) {
            nextHop = parseIPv4(*nextHopAddress);
        }
    }
};

class RoutingTable {
private:
    std::vector<Route> routes;

public:
    void addRoute(
        const std::string& cidr,
        std::optional<std::string> nextHop,
        const std::string& interfaceName,
        int metric,
        const std::string& description
    ) {
        routes.emplace_back(
            cidr,
            nextHop,
            interfaceName,
            metric,
            description
        );
    }

    const std::vector<Route>& allRoutes() const {
        return routes;
    }

    std::optional<std::reference_wrapper<const Route>>
    lookup(IPv4 destination) const {

        const Route* best = nullptr;

        for (const auto& route : routes) {
            if (!route.network.contains(destination)) {
                continue;
            }

            if (best == nullptr) {
                best = &route;
                continue;
            }

            if (route.network.prefixLength >
                best->network.prefixLength) {
                best = &route;
                continue;
            }

            if (route.network.prefixLength ==
                best->network.prefixLength &&
                route.metric < best->metric) {
                best = &route;
            }
        }

        if (best == nullptr) {
            return std::nullopt;
        }

        return std::cref(*best);
    }

    void print() const {
        std::cout << "\nRouting table\n";

        std::vector<const Route*> ordered;

        for (const auto& route : routes) {
            ordered.push_back(&route);
        }

        std::sort(
            ordered.begin(),
            ordered.end(),
            [](const Route* left, const Route* right) {
                if (left->network.prefixLength !=
                    right->network.prefixLength) {
                    return left->network.prefixLength >
                           right->network.prefixLength;
                }

                return left->metric < right->metric;
            }
        );

        for (const Route* route : ordered) {
            std::cout
                << std::left
                << std::setw(20)
                << route->network.toString();

            if (route->nextHop.has_value()) {
                std::cout
                    << " via "
                    << std::setw(16)
                    << ipv4ToString(*route->nextHop);
            } else {
                std::cout
                    << " via "
                    << std::setw(16)
                    << "direct";
            }

            std::cout
                << " dev "
                << std::setw(10)
                << route->interfaceName
                << " metric "
                << route->metric
                << "  "
                << route->description
                << "\n";
        }
    }
};

// ============================================================================
// 4. ROUTER
// ============================================================================

class Router {
private:
    std::string name;
    RoutingTable routingTable;
    bool forwardingEnabled = true;

public:
    explicit Router(std::string name)
        : name(std::move(name)) {}

    const std::string& getName() const {
        return name;
    }

    RoutingTable& table() {
        return routingTable;
    }

    const RoutingTable& table() const {
        return routingTable;
    }

    void setForwardingEnabled(bool enabled) {
        forwardingEnabled = enabled;
    }

    const Route& forward(Packet& packet) const {
        if (!forwardingEnabled) {
            throw std::runtime_error(
                name + ": IP forwarding is disabled"
            );
        }

        if (packet.ttl <= 1) {
            throw std::runtime_error(
                name + ": TTL expired"
            );
        }

        --packet.ttl;

        const auto result =
            routingTable.lookup(packet.destinationIP);

        if (!result.has_value()) {
            throw std::runtime_error(
                name + ": no route to " +
                ipv4ToString(packet.destinationIP)
            );
        }

        return result->get();
    }
};

// ============================================================================
// 5. NAT/PAT
// ============================================================================

struct NatKey {
    IPv4 privateIP;
    std::uint16_t privatePort;
    IPv4 remoteIP;
    std::uint16_t remotePort;
    std::string protocol;

    bool operator<(const NatKey& other) const {
        return std::tie(
            privateIP,
            privatePort,
            remoteIP,
            remotePort,
            protocol
        ) < std::tie(
            other.privateIP,
            other.privatePort,
            other.remoteIP,
            other.remotePort,
            other.protocol
        );
    }
};

struct InboundKey {
    IPv4 publicIP;
    std::uint16_t publicPort;
    std::string protocol;

    bool operator<(const InboundKey& other) const {
        return std::tie(
            publicIP,
            publicPort,
            protocol
        ) < std::tie(
            other.publicIP,
            other.publicPort,
            other.protocol
        );
    }
};

struct NatMapping {
    IPv4 privateIP;
    std::uint16_t privatePort;

    IPv4 publicIP;
    std::uint16_t publicPort;

    IPv4 remoteIP;
    std::uint16_t remotePort;

    std::string protocol;

    std::uint64_t packetCount = 0;

    std::string privateEndpoint() const {
        return ipv4ToString(privateIP) +
               ":" +
               std::to_string(privatePort);
    }

    std::string publicEndpoint() const {
        return ipv4ToString(publicIP) +
               ":" +
               std::to_string(publicPort);
    }
};

class PatGateway {
private:
    IPv4 publicIP;
    std::uint16_t firstPort;
    std::uint16_t lastPort;
    std::uint16_t nextPort;

    std::map<NatKey, NatMapping> outbound;
    std::map<InboundKey, NatKey> inbound;

    std::uint16_t allocatePort(
        const std::string& protocol
    ) {
        const std::uint32_t capacity =
            static_cast<std::uint32_t>(lastPort) -
            static_cast<std::uint32_t>(firstPort) +
            1;

        for (std::uint32_t attempt = 0;
             attempt < capacity;
             ++attempt) {

            const std::uint16_t candidate = nextPort;

            if (nextPort == lastPort) {
                nextPort = firstPort;
            } else {
                ++nextPort;
            }

            InboundKey key{
                publicIP,
                candidate,
                protocol
            };

            if (!inbound.contains(key)) {
                return candidate;
            }
        }

        throw std::runtime_error(
            "PAT public port pool exhausted"
        );
    }

public:
    PatGateway(
        const std::string& publicAddress,
        std::uint16_t firstPort = 40000,
        std::uint16_t lastPort = 49999
    )
        : publicIP(parseIPv4(publicAddress)),
          firstPort(firstPort),
          lastPort(lastPort),
          nextPort(firstPort) {

        if (firstPort > lastPort) {
            throw std::invalid_argument(
                "Invalid NAT port range"
            );
        }
    }

    Packet translateOutbound(const Packet& original) {
        if (!original.sourcePort.has_value() ||
            !original.destinationPort.has_value()) {
            throw std::invalid_argument(
                "PAT requires transport-layer ports"
            );
        }

        NatKey key{
            original.sourceIP,
            *original.sourcePort,
            original.destinationIP,
            *original.destinationPort,
            original.protocol
        };

        auto iterator = outbound.find(key);

        if (iterator == outbound.end()) {
            const std::uint16_t publicPort =
                allocatePort(original.protocol);

            NatMapping mapping{
                original.sourceIP,
                *original.sourcePort,
                publicIP,
                publicPort,
                original.destinationIP,
                *original.destinationPort,
                original.protocol,
                0
            };

            iterator =
                outbound.emplace(
                    key,
                    mapping
                ).first;

            inbound.emplace(
                InboundKey{
                    publicIP,
                    publicPort,
                    original.protocol
                },
                key
            );
        }

        iterator->second.packetCount++;

        Packet translated = original;
        translated.sourceIP = publicIP;
        translated.sourcePort =
            iterator->second.publicPort;

        return translated;
    }

    Packet translateInbound(const Packet& original) const {
        if (!original.destinationPort.has_value()) {
            throw std::invalid_argument(
                "Inbound PAT requires destination port"
            );
        }

        const InboundKey inboundKey{
            original.destinationIP,
            *original.destinationPort,
            original.protocol
        };

        const auto inboundIterator =
            inbound.find(inboundKey);

        if (inboundIterator == inbound.end()) {
            throw std::runtime_error(
                "No matching PAT state"
            );
        }

        const auto mappingIterator =
            outbound.find(inboundIterator->second);

        if (mappingIterator == outbound.end()) {
            throw std::runtime_error(
                "PAT state is inconsistent"
            );
        }

        Packet restored = original;

        restored.destinationIP =
            mappingIterator->second.privateIP;

        restored.destinationPort =
            mappingIterator->second.privatePort;

        return restored;
    }

    void printTable() const {
        std::cout << "\nPAT Translation Table\n";

        if (outbound.empty()) {
            std::cout << "(empty)\n";
            return;
        }

        for (const auto& [key, mapping] : outbound) {
            std::cout
                << std::left
                << std::setw(23)
                << mapping.privateEndpoint()
                << " -> "
                << std::setw(23)
                << mapping.publicEndpoint()
                << " -> "
                << ipv4ToString(mapping.remoteIP)
                << ":"
                << mapping.remotePort
                << " "
                << mapping.protocol
                << " packets="
                << mapping.packetCount
                << "\n";
        }
    }
};

// ============================================================================
// 6. TRACEROUTE MODEL
// ============================================================================

struct TraceHop {
    IPv4 address;
    std::string name;
    double delayMilliseconds;
};

std::vector<std::string> simulateTraceroute(
    const std::vector<TraceHop>& hops,
    unsigned int maxHops = 30
) {
    std::vector<std::string> result;

    for (unsigned int ttl = 1;
         ttl <= maxHops;
         ++ttl) {

        if (ttl > hops.size()) {
            std::ostringstream line;
            line
                << std::setw(2)
                << ttl
                << "  * * * no response";

            result.push_back(line.str());
            break;
        }

        const auto& hop = hops[ttl - 1];

        std::ostringstream line;

        line
            << std::setw(2)
            << ttl
            << "  "
            << std::setw(16)
            << ipv4ToString(hop.address)
            << "  "
            << std::fixed
            << std::setprecision(2)
            << std::setw(7)
            << hop.delayMilliseconds
            << " ms  "
            << hop.name;

        if (ttl < hops.size()) {
            line
                << " (TTL expired -> ICMP Time Exceeded)";
        } else {
            line
                << " (destination reached)";
        }

        result.push_back(line.str());

        if (ttl == hops.size()) {
            break;
        }
    }

    return result;
}

// ============================================================================
// 7. HOST MODEL
// ============================================================================

class Host {
private:
    std::string name;
    IPv4 address;
    Network network;
    IPv4 gateway;

public:
    Host(
        std::string name,
        const std::string& address,
        const std::string& network,
        const std::string& gateway
    )
        : name(std::move(name)),
          address(parseIPv4(address)),
          network(network),
          gateway(parseIPv4(gateway)) {}

    const std::string& getName() const {
        return name;
    }

    IPv4 getAddress() const {
        return address;
    }

    const Network& getNetwork() const {
        return network;
    }

    IPv4 getGateway() const {
        return gateway;
    }

    bool directlyReachable(IPv4 destination) const {
        return network.contains(destination);
    }

    IPv4 nextHop(IPv4 destination) const {
        return directlyReachable(destination)
            ? destination
            : gateway;
    }
};

// ============================================================================
// 8. NETWORK TOPOLOGY
// ============================================================================

struct Link {
    std::string left;
    std::string right;
    Network network;

    Link(
        std::string left,
        std::string right,
        const std::string& network
    )
        : left(std::move(left)),
          right(std::move(right)),
          network(network) {}
};

class EnterpriseNetwork {
private:
    Host client;
    Host server;

    Router edgeRouter;
    Router ispRouter;

    PatGateway natGateway;

    std::vector<Link> links;

public:
    EnterpriseNetwork()
        : client(
            "LAN-Client",
            "192.168.50.10",
            "192.168.50.0/24",
            "192.168.50.1"
        ),
          server(
            "Internet-Server",
            "198.51.100.20",
            "198.51.100.0/24",
            "198.51.100.1"
        ),
          edgeRouter("Edge-Router"),
          ispRouter("ISP-Router"),
          natGateway("203.0.113.2") {

        edgeRouter.table().addRoute(
            "192.168.50.0/24",
            std::nullopt,
            "lan",
            0,
            "direct private LAN"
        );

        edgeRouter.table().addRoute(
            "203.0.113.0/30",
            std::nullopt,
            "wan",
            0,
            "direct ISP transit"
        );

        edgeRouter.table().addRoute(
            "0.0.0.0/0",
            std::optional<std::string>("203.0.113.1"),
            "wan",
            10,
            "default Internet route"
        );

        ispRouter.table().addRoute(
            "203.0.113.0/30",
            std::nullopt,
            "customer",
            0,
            "customer connection"
        );

        ispRouter.table().addRoute(
            "198.51.100.0/24",
            std::nullopt,
            "internet",
            0,
            "Internet server network"
        );

        links.emplace_back(
            "LAN-Client",
            "Edge-Router",
            "192.168.50.0/24"
        );

        links.emplace_back(
            "Edge-Router",
            "ISP-Router",
            "203.0.113.0/30"
        );

        links.emplace_back(
            "ISP-Router",
            "Internet-Server",
            "198.51.100.0/24"
        );
    }

    const Host& getClient() const {
        return client;
    }

    const Host& getServer() const {
        return server;
    }

    Router& getEdgeRouter() {
        return edgeRouter;
    }

    Router& getIspRouter() {
        return ispRouter;
    }

    PatGateway& getNatGateway() {
        return natGateway;
    }

    void printTopology() const {
        std::cout << "\nNetwork Topology\n";

        for (const auto& link : links) {
            std::cout
                << link.left
                << " <-> "
                << link.right
                << " ["
                << link.network.toString()
                << "]\n";
        }
    }
};

// ============================================================================
// 9. SECTION HELPERS
// ============================================================================

void section(const std::string& title) {
    std::cout << "\n"
              << std::string(78, '=')
              << "\n"
              << title
              << "\n"
              << std::string(78, '=')
              << "\n";
}

void subsection(const std::string& title) {
    std::cout << "\n--- " << title << " ---\n";
}

// ============================================================================
// 10. ADDRESSING DEMONSTRATION
// ============================================================================

void demonstrateAddressing() {
    section("1. IPv4 Addressing and CIDR");

    const std::vector<std::pair<std::string, std::string>> examples{
        {"192.168.1.10", "192.168.1.0/24"},
        {"10.20.30.40", "10.0.0.0/8"},
        {"172.16.5.20", "172.16.0.0/12"},
        {"8.8.8.8", "0.0.0.0/0"}
    };

    for (const auto& [addressText, networkText] : examples) {
        const IPv4 address = parseIPv4(addressText);
        const Network network(networkText);

        std::cout
            << std::left
            << std::setw(16)
            << addressText
            << " in "
            << std::setw(18)
            << network.toString()
            << " = "
            << std::boolalpha
            << network.contains(address)
            << "\n";
    }

    subsection("Private address space");

    for (const auto& cidr : {
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16"
    }) {
        std::cout
            << cidr
            << " is RFC 1918 private address space\n";
    }

    subsection("Prefix examples");

    for (unsigned int prefix : {8u, 16u, 24u, 30u, 32u}) {
        const IPv4 mask = prefixMask(prefix);

        const std::uint64_t addressCount =
            std::uint64_t{1}
            << (32 - prefix);

        std::cout
            << "/"
            << prefix
            << " mask="
            << ipv4ToString(mask)
            << " addresses="
            << addressCount
            << "\n";
    }
}

// ============================================================================
// 11. ROUTING TABLE DEMONSTRATION
// ============================================================================

void demonstrateRouting() {
    section("2. Routing Tables and Longest-Prefix Matching");

    RoutingTable table;

    table.addRoute(
        "0.0.0.0/0",
        std::optional<std::string>("192.168.1.1"),
        "eth0",
        100,
        "default route"
    );

    table.addRoute(
        "10.0.0.0/8",
        std::optional<std::string>("192.168.1.254"),
        "eth1",
        100,
        "enterprise network"
    );

    table.addRoute(
        "10.10.0.0/16",
        std::optional<std::string>("192.168.1.253"),
        "eth2",
        100,
        "regional network"
    );

    table.addRoute(
        "10.10.20.0/24",
        std::optional<std::string>("192.168.1.252"),
        "eth3",
        50,
        "specific subnet"
    );

    table.print();

    subsection("Lookup");

    for (const auto& destination : {
        "10.10.20.55",
        "10.10.40.10",
        "10.50.1.1",
        "8.8.8.8"
    }) {
        const auto result =
            table.lookup(parseIPv4(destination));

        if (!result.has_value()) {
            std::cout
                << destination
                << " -> no route\n";
            continue;
        }

        const Route& route = result->get();

        std::cout
            << destination
            << " -> "
            << route.network.toString()
            << " via ";

        if (route.nextHop.has_value()) {
            std::cout << ipv4ToString(*route.nextHop);
        } else {
            std::cout << "direct";
        }

        std::cout
            << " dev "
            << route.interfaceName
            << "\n";
    }
}

// ============================================================================
// 12. DEFAULT GATEWAY
// ============================================================================

void demonstrateGateway() {
    section("3. Default Gateway");

    Host host(
        "Client",
        "192.168.1.50",
        "192.168.1.0/24",
        "192.168.1.1"
    );

    for (const auto& destinationText : {
        "192.168.1.75",
        "192.168.2.75",
        "8.8.8.8"
    }) {
        const IPv4 destination =
            parseIPv4(destinationText);

        if (host.directlyReachable(destination)) {
            std::cout
                << destinationText
                << " is directly reachable on "
                << host.getNetwork().toString()
                << "\n";
        } else {
            std::cout
                << destinationText
                << " is outside "
                << host.getNetwork().toString()
                << "; next hop="
                << ipv4ToString(host.getGateway())
                << "\n";
        }
    }
}

// ============================================================================
// 13. ROUTER FORWARDING
// ============================================================================

void demonstrateForwarding() {
    section("4. Router Forwarding");

    Router router("R1");

    router.table().addRoute(
        "192.168.10.0/24",
        std::nullopt,
        "lan0",
        0,
        "direct LAN"
    );

    router.table().addRoute(
        "192.168.20.0/24",
        std::nullopt,
        "lan1",
        0,
        "direct server LAN"
    );

    router.table().addRoute(
        "0.0.0.0/0",
        std::optional<std::string>("192.168.10.254"),
        "wan0",
        100,
        "default"
    );

    router.table().print();

    Packet packet{
        parseIPv4("192.168.10.50"),
        parseIPv4("192.168.20.80"),
        static_cast<std::uint16_t>(50000),
        static_cast<std::uint16_t>(443),
        "TCP",
        64,
        "application data"
    };

    std::cout
        << "\nBefore forwarding: "
        << packet.summary()
        << "\n";

    const Route& route =
        router.forward(packet);

    std::cout
        << "Selected route: "
        << route.network.toString()
        << " via "
        << (route.nextHop.has_value()
                ? ipv4ToString(*route.nextHop)
                : "direct")
        << " dev "
        << route.interfaceName
        << "\n";

    std::cout
        << "After forwarding: "
        << packet.summary()
        << "\n";
}

// ============================================================================
// 14. NAT DEMONSTRATION
// ============================================================================

void demonstrateNat() {
    section("5. NAT/PAT");

    PatGateway nat("203.0.113.10");

    const std::vector<Packet> privatePackets{
        {
            parseIPv4("192.168.1.10"),
            parseIPv4("93.184.216.34"),
            static_cast<std::uint16_t>(51000),
            static_cast<std::uint16_t>(443),
            "TCP",
            64,
            "HTTPS"
        },
        {
            parseIPv4("192.168.1.11"),
            parseIPv4("93.184.216.34"),
            static_cast<std::uint16_t>(51001),
            static_cast<std::uint16_t>(443),
            "TCP",
            64,
            "HTTPS"
        },
        {
            parseIPv4("192.168.1.10"),
            parseIPv4("142.250.72.14"),
            static_cast<std::uint16_t>(51002),
            static_cast<std::uint16_t>(443),
            "TCP",
            64,
            "HTTPS"
        }
    };

    std::vector<Packet> translated;

    for (const auto& packet : privatePackets) {
        Packet result =
            nat.translateOutbound(packet);

        translated.push_back(result);

        std::cout
            << "Before NAT: "
            << packet.summary()
            << "\n";

        std::cout
            << "After NAT:  "
            << result.summary()
            << "\n\n";
    }

    nat.printTable();

    Packet response{
        parseIPv4("93.184.216.34"),
        translated[0].sourceIP,
        static_cast<std::uint16_t>(443),
        translated[0].sourcePort,
        "TCP",
        64,
        "HTTPS response"
    };

    Packet restored =
        nat.translateInbound(response);

    std::cout
        << "\nBefore reverse NAT: "
        << response.summary()
        << "\n";

    std::cout
        << "After reverse NAT:  "
        << restored.summary()
        << "\n";
}

// ============================================================================
// 15. COMPLETE PRIVATE-TO-PUBLIC CASE STUDY
// ============================================================================

void demonstrateCompleteCaseStudy() {
    section("6. Industry-Style Private-to-Public Communication");

    EnterpriseNetwork network;

    network.printTopology();

    const Host& client =
        network.getClient();

    const Host& server =
        network.getServer();

    Packet packet{
        client.getAddress(),
        server.getAddress(),
        static_cast<std::uint16_t>(52000),
        static_cast<std::uint16_t>(443),
        "TCP",
        8,
        "HTTPS request"
    };

    subsection("Stage 1: Client creates the packet");

    std::cout
        << packet.summary()
        << "\n";

    subsection("Stage 2: Client chooses next hop");

    if (client.directlyReachable(packet.destinationIP)) {
        std::cout
            << "Destination is local; direct delivery is possible.\n";
    } else {
        std::cout
            << "Destination is remote; use default gateway "
            << ipv4ToString(client.getGateway())
            << "\n";
    }

    subsection("Stage 3: Edge router performs NAT");

    Packet translated =
        network.getNatGateway()
            .translateOutbound(packet);

    std::cout
        << "Before NAT: "
        << packet.summary()
        << "\n";

    std::cout
        << "After NAT:  "
        << translated.summary()
        << "\n";

    subsection("Stage 4: Edge router performs route lookup");

    auto edgeRoute =
        network.getEdgeRouter()
            .table()
            .lookup(translated.destinationIP);

    if (!edgeRoute.has_value()) {
        throw std::runtime_error(
            "Edge router has no route to Internet"
        );
    }

    std::cout
        << edgeRoute->get().network.toString()
        << " via "
        << (edgeRoute->get().nextHop.has_value()
                ? ipv4ToString(*edgeRoute->get().nextHop)
                : "direct")
        << " dev "
        << edgeRoute->get().interfaceName
        << "\n";

    subsection("Stage 5: ISP router performs route lookup");

    auto ispRoute =
        network.getIspRouter()
            .table()
            .lookup(translated.destinationIP);

    if (!ispRoute.has_value()) {
        throw std::runtime_error(
            "ISP router cannot reach destination"
        );
    }

    std::cout
        << ispRoute->get().network.toString()
        << " via "
        << (ispRoute->get().nextHop.has_value()
                ? ipv4ToString(*ispRoute->get().nextHop)
                : "direct")
        << " dev "
        << ispRoute->get().interfaceName
        << "\n";

    subsection("Stage 6: Internet server receives packet");

    std::cout
        << server.getName()
        << " receives traffic for "
        << translated.destinationIP
        << ":"
        << translated.destinationPort.value()
        << "\n";

    subsection("Stage 7: Server sends response");

    Packet response{
        server.getAddress(),
        translated.sourceIP,
        static_cast<std::uint16_t>(443),
        translated.sourcePort,
        "TCP",
        8,
        "HTTPS response"
    };

    std::cout
        << "Response before reverse NAT: "
        << response.summary()
        << "\n";

    Packet restored =
        network.getNatGateway()
            .translateInbound(response);

    std::cout
        << "Response after reverse NAT:  "
        << restored.summary()
        << "\n";

    std::cout
        << "\nComplete logical path:\n"
        << "private client -> gateway -> NAT -> ISP -> "
        << "Internet server -> ISP -> public NAT endpoint -> "
        << "reverse NAT -> private client\n";
}

// ============================================================================
// 16. TRACEROUTE DEMONSTRATION
// ============================================================================

void demonstrateTraceroute() {
    section("7. Traceroute and TTL");

    const std::vector<TraceHop> hops{
        {
            parseIPv4("192.168.50.1"),
            "Edge-Router",
            1.2
        },
        {
            parseIPv4("203.0.113.1"),
            "ISP-Router",
            8.7
        },
        {
            parseIPv4("198.51.100.1"),
            "Transit-Router",
            17.3
        },
        {
            parseIPv4("198.51.100.20"),
            "Internet-Server",
            22.4
        }
    };

    for (const auto& line :
         simulateTraceroute(hops)) {
        std::cout
            << line
            << "\n";
    }

    std::cout
        << "\nTraceroute uses probes with increasing TTL values. "
        << "Intermediate routers can return ICMP Time Exceeded when "
        << "a probe's TTL reaches zero. The destination eventually "
        << "produces a destination-specific response.\n";
}

// ============================================================================
// 17. FAILURE ANALYSIS
// ============================================================================

void demonstrateFailures() {
    section("8. Failure Analysis");

    subsection("No route");

    RoutingTable table;

    table.addRoute(
        "192.168.1.0/24",
        std::nullopt,
        "eth0",
        0,
        "local"
    );

    auto result =
        table.lookup(parseIPv4("10.0.0.1"));

    std::cout
        << "10.0.0.1 -> "
        << (result.has_value() ? "route exists" : "NO ROUTE")
        << "\n";

    subsection("Equal prefix, lower metric wins");

    RoutingTable redundant;

    redundant.addRoute(
        "10.20.0.0/16",
        std::optional<std::string>("192.0.2.10"),
        "eth0",
        50,
        "primary"
    );

    redundant.addRoute(
        "10.20.0.0/16",
        std::optional<std::string>("192.0.2.11"),
        "eth1",
        100,
        "backup"
    );

    auto redundantResult =
        redundant.lookup(parseIPv4("10.20.1.1"));

    assert(redundantResult.has_value());

    std::cout
        << "Selected next hop: "
        << ipv4ToString(
            redundantResult->get().nextHop.value()
        )
        << "\n";

    subsection("TTL expiration");

    Router loopRouter("Loop-Router");

    loopRouter.table().addRoute(
        "0.0.0.0/0",
        std::optional<std::string>("192.0.2.1"),
        "wan",
        100,
        "default"
    );

    Packet packet{
        parseIPv4("10.0.0.10"),
        parseIPv4("8.8.8.8"),
        static_cast<std::uint16_t>(50000),
        static_cast<std::uint16_t>(443),
        "TCP",
        1,
        ""
    };

    try {
        loopRouter.forward(packet);
    } catch (const std::exception& exception) {
        std::cout
            << "Expected failure: "
            << exception.what()
            << "\n";
    }

    subsection("Missing NAT state");

    PatGateway nat("203.0.113.50");

    Packet response{
        parseIPv4("198.51.100.10"),
        parseIPv4("203.0.113.50"),
        static_cast<std::uint16_t>(443),
        static_cast<std::uint16_t>(41000),
        "TCP",
        64,
        ""
    };

    try {
        nat.translateInbound(response);
    } catch (const std::exception& exception) {
        std::cout
            << "Expected failure: "
            << exception.what()
            << "\n";
    }

    subsection("Operational failure categories");

    for (const auto& failure : {
        "incorrect subnet prefix",
        "wrong default gateway",
        "missing route",
        "incorrect next hop",
        "routing loop",
        "TTL expiration",
        "NAT state timeout",
        "NAT port exhaustion",
        "firewall or ACL filtering",
        "asymmetric routing",
        "MTU problems",
        "DNS failure mistaken for routing failure"
    }) {
        std::cout
            << "- "
            << failure
            << "\n";
    }
}

// ============================================================================
// 18. ROUTING PROTOCOLS
// ============================================================================

void explainRoutingProtocols() {
    section("9. Static and Dynamic Routing");

    const std::vector<std::tuple<
        std::string,
        std::string,
        std::string
    >> protocols{
        {
            "Static",
            "Administrator-configured routes",
            "Stable or intentionally controlled networks"
        },
        {
            "RIP",
            "Distance-vector routing using hop count",
            "Historical/small networks"
        },
        {
            "OSPF",
            "Link-state interior gateway protocol",
            "Enterprise and data-center networks"
        },
        {
            "IS-IS",
            "Link-state interior gateway protocol",
            "Large infrastructure networks"
        },
        {
            "BGP",
            "Path-vector inter-domain routing",
            "Internet-scale autonomous-system routing"
        }
    };

    for (const auto& [name, mechanism, use] : protocols) {
        std::cout
            << name
            << ": "
            << mechanism
            << "\n  Typical use: "
            << use
            << "\n\n";
    }

    std::cout
        << "A routing table is forwarding information. "
        << "A routing protocol is one mechanism for learning or "
        << "maintaining routes.\n";
}

// ============================================================================
// 19. COMPLEXITY DISCUSSION
// ============================================================================

void discussComplexity() {
    section("10. Performance and Complexity");

    std::cout
        << "The educational RoutingTable::lookup implementation scans "
        << "every route, so a lookup is O(R), where R is the number of "
        << "stored routes.\n\n";

    std::cout
        << "Production routers can use specialized structures and hardware "
        << "forwarding mechanisms to perform longest-prefix matching much "
        << "more efficiently than a naive linear scan.\n\n";

    std::cout
        << "The PAT implementation uses ordered maps for educational clarity. "
        << "Typical lookup and insertion costs are O(log N), where N is "
        << "the number of tracked flows. Production systems may use highly "
        << "optimized hash tables, hardware acceleration, or specialized "
        << "connection-tracking structures.\n\n";

    std::cout
        << "Memory consumption is also important: every active NAT flow "
        << "requires state containing endpoint information, translated "
        << "ports, timers, protocol state, and associated metadata.\n";
}

// ============================================================================
// 20. SECURITY CONSIDERATIONS
// ============================================================================

void discussSecurity() {
    section("11. Security Considerations");

    const std::vector<std::pair<
        std::string,
        std::string
    >> topics{
        {
            "NAT is not a firewall",
            "Translation changes addressing but explicit security policy "
            "normally comes from firewall and ACL rules."
        },
        {
            "Private does not mean trusted",
            "RFC 1918 addresses identify private addressing space; they "
            "do not authenticate users or authorize traffic."
        },
        {
            "Routing manipulation",
            "Unauthorized route changes can redirect, blackhole, or "
            "otherwise disrupt traffic."
        },
        {
            "Traceroute visibility",
            "Infrastructure that responds to probes can expose topology "
            "information."
        },
        {
            "NAT state exhaustion",
            "Excessive connection creation can consume translation state "
            "or available ports."
        },
        {
            "Management-plane security",
            "Router configuration and routing-control interfaces need "
            "access protection independent of ordinary packet forwarding."
        }
    };

    for (const auto& [name, explanation] : topics) {
        std::cout
            << "\n"
            << name
            << ":\n  "
            << explanation
            << "\n";
    }
}

// ============================================================================
// 21. DIAGNOSTIC WORKFLOW
// ============================================================================

void diagnosticWorkflow() {
    section("12. Practical Troubleshooting Workflow");

    const std::vector<std::string> steps{
        "Confirm interface state.",
        "Confirm IP address and prefix.",
        "Confirm destination address.",
        "Determine local versus routed destination.",
        "Inspect the host routing table.",
        "Verify the default gateway.",
        "Test gateway reachability.",
        "Inspect routing tables on relevant routers.",
        "Check NAT/SNAT/PAT state.",
        "Check firewall and ACL rules.",
        "Use traceroute or tracert to observe the path.",
        "Check DNS separately.",
        "Verify the return route.",
        "Check MTU when packet-size behavior is suspicious."
    };

    for (std::size_t index = 0;
         index < steps.size();
         ++index) {
        std::cout
            << index + 1
            << ". "
            << steps[index]
            << "\n";
    }

    std::cout
        << "\nLinux examples:\n"
        << "  ip addr\n"
        << "  ip route\n"
        << "  ip route get 8.8.8.8\n"
        << "  ping 8.8.8.8\n"
        << "  traceroute 8.8.8.8\n\n"
        << "Windows examples:\n"
        << "  ipconfig\n"
        << "  route print\n"
        << "  ping 8.8.8.8\n"
        << "  tracert 8.8.8.8\n";
}

// ============================================================================
// 22. SELF TESTS
// ============================================================================

void runSelfTests() {
    section("13. Self Tests");

    RoutingTable table;

    table.addRoute(
        "0.0.0.0/0",
        std::optional<std::string>("192.168.1.1"),
        "default",
        100,
        "default"
    );

    table.addRoute(
        "10.0.0.0/8",
        std::optional<std::string>("192.168.1.2"),
        "private",
        100,
        "private"
    );

    table.addRoute(
        "10.1.0.0/16",
        std::optional<std::string>("192.168.1.3"),
        "regional",
        100,
        "regional"
    );

    table.addRoute(
        "10.1.2.0/24",
        std::optional<std::string>("192.168.1.4"),
        "local",
        100,
        "local"
    );

    auto result =
        table.lookup(parseIPv4("10.1.2.99"));

    assert(result.has_value());
    assert(result->get().network.prefixLength == 24);

    result =
        table.lookup(parseIPv4("10.1.99.99"));

    assert(result.has_value());
    assert(result->get().network.prefixLength == 16);

    result =
        table.lookup(parseIPv4("10.99.99.99"));

    assert(result.has_value());
    assert(result->get().network.prefixLength == 8);

    result =
        table.lookup(parseIPv4("8.8.8.8"));

    assert(result.has_value());
    assert(result->get().network.prefixLength == 0);

    PatGateway nat(
        "203.0.113.100",
        40000,
        40010
    );

    Packet first{
        parseIPv4("192.168.1.10"),
        parseIPv4("198.51.100.20"),
        static_cast<std::uint16_t>(50000),
        static_cast<std::uint16_t>(443),
        "TCP",
        64,
        ""
    };

    Packet second{
        parseIPv4("192.168.1.11"),
        parseIPv4("198.51.100.20"),
        static_cast<std::uint16_t>(50000),
        static_cast<std::uint16_t>(443),
        "TCP",
        64,
        ""
    };

    Packet translatedFirst =
        nat.translateOutbound(first);

    Packet translatedSecond =
        nat.translateOutbound(second);

    assert(
        translatedFirst.sourceIP ==
        parseIPv4("203.0.113.100")
    );

    assert(
        translatedSecond.sourceIP ==
        parseIPv4("203.0.113.100")
    );

    assert(
        translatedFirst.sourcePort !=
        translatedSecond.sourcePort
    );

    Packet response{
        parseIPv4("198.51.100.20"),
        parseIPv4("203.0.113.100"),
        static_cast<std::uint16_t>(443),
        translatedFirst.sourcePort,
        "TCP",
        64,
        ""
    };

    Packet restored =
        nat.translateInbound(response);

    assert(
        restored.destinationIP ==
        first.sourceIP
    );

    assert(
        restored.destinationPort ==
        first.sourcePort
    );

    std::cout
        << "All C++ routing and NAT tests passed.\n";
}

// ============================================================================
// 23. MAIN
// ============================================================================

int main() {
    try {
        demonstrateAddressing();
        demonstrateRouting();
        demonstrateGateway();
        demonstrateForwarding();
        demonstrateNat();
        demonstrateCompleteCaseStudy();
        demonstrateTraceroute();
        demonstrateFailures();
        explainRoutingProtocols();
        discussComplexity();
        discussSecurity();
        diagnosticWorkflow();
        runSelfTests();

        section("14. Core Operational Model");

        std::cout
            << "Host decision:\n"
            << "  address -> subnet check -> route lookup -> next hop\n\n"

            << "Router decision:\n"
            << "  receive -> TTL decrement -> longest-prefix match -> "
            << "policy/NAT -> forward\n\n"

            << "Private-to-public communication:\n"
            << "  private host -> gateway -> PAT -> public network -> server\n"
            << "  server -> public NAT endpoint -> reverse PAT -> private host\n\n"

            << "Troubleshooting:\n"
            << "  address -> prefix -> gateway -> route -> next hop -> "
            << "NAT -> ACL -> return path\n";

        return 0;
    }
    catch (const std::exception& exception) {
        std::cerr
            << "Fatal error: "
            << exception.what()
            << "\n";

        return 1;
    }
}
