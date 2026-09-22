/*
 * OSI Model: Industry-Style C++17 Case Study
 *
 * Scenario:
 * A small enterprise network contains client devices, an access switch,
 * a router, an application server, and a monitoring component.
 *
 * The program models packet construction, MAC learning, routing,
 * transport connections, application requests, diagnostics, validation,
 * security controls, and performance metrics.
 *
 * Compile:
 *   g++ -std=c++17 -O2 osi_models.cpp -o osi_models
 *
 * Run:
 *   ./osi_models
 */

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

using namespace std;

enum class OSILayer {
    Physical = 1,
    DataLink = 2,
    Network = 3,
    Transport = 4,
    Session = 5,
    Presentation = 6,
    Application = 7
};

string layerName(OSILayer layer) {
    switch (layer) {
        case OSILayer::Physical: return "Physical";
        case OSILayer::DataLink: return "Data Link";
        case OSILayer::Network: return "Network";
        case OSILayer::Transport: return "Transport";
        case OSILayer::Session: return "Session";
        case OSILayer::Presentation: return "Presentation";
        case OSILayer::Application: return "Application";
    }

    return "Unknown";
}

string pduName(OSILayer layer) {
    switch (layer) {
        case OSILayer::Physical: return "Bits";
        case OSILayer::DataLink: return "Frame";
        case OSILayer::Network: return "Packet";
        case OSILayer::Transport: return "Segment/Datagram";
        case OSILayer::Session:
        case OSILayer::Presentation:
        case OSILayer::Application:
            return "Data";
    }

    return "Unknown";
}

void title(const string& text) {
    cout << "\n" << string(78, '=') << "\n";
    cout << text << "\n";
    cout << string(78, '=') << "\n";
}

class IPv4Address {
private:
    uint32_t value;

public:
    explicit IPv4Address(uint32_t value = 0) : value(value) {}

    static IPv4Address parse(const string& text) {
        unsigned int a, b, c, d;
        char first, second, third;

        stringstream stream(text);

        if (!(stream >> a >> first >> b >> second >> c >> third >> d) ||
            first != '.' || second != '.' || third != '.' ||
            a > 255 || b > 255 || c > 255 || d > 255) {
            throw invalid_argument("Invalid IPv4 address: " + text);
        }

        uint32_t value =
            (a << 24) |
            (b << 16) |
            (c << 8) |
            d;

        return IPv4Address(value);
    }

    uint32_t raw() const {
        return value;
    }

    string toString() const {
        ostringstream output;

        output
            << ((value >> 24) & 255) << "."
            << ((value >> 16) & 255) << "."
            << ((value >> 8) & 255) << "."
            << (value & 255);

        return output.str();
    }

    bool operator==(const IPv4Address& other) const {
        return value == other.value;
    }
};

class CIDRNetwork {
private:
    IPv4Address networkAddress;
    int prefixLength;

public:
    CIDRNetwork(IPv4Address address, int prefix)
        : networkAddress(address), prefixLength(prefix) {

        if (prefix < 0 || prefix > 32) {
            throw invalid_argument("CIDR prefix must be between 0 and 32.");
        }
    }

    bool contains(IPv4Address address) const {
        if (prefixLength == 0) {
            return true;
        }

        uint32_t mask = 0xFFFFFFFFu << (32 - prefixLength);

        return (address.raw() & mask) ==
               (networkAddress.raw() & mask);
    }

    int prefix() const {
        return prefixLength;
    }

    string toString() const {
        return networkAddress.toString() + "/" +
               to_string(prefixLength);
    }
};

struct EthernetFrame {
    string sourceMAC;
    string destinationMAC;
    uint16_t etherType;
    string payload;
};

struct IPPacket {
    IPv4Address source;
    IPv4Address destination;
    uint8_t ttl;
    uint8_t protocol;
    string payload;

    bool forward() {
        if (ttl == 0) {
            return false;
        }

        --ttl;
        return ttl > 0;
    }
};

struct TCPSegment {
    uint16_t sourcePort;
    uint16_t destinationPort;
    uint32_t sequenceNumber;
    uint32_t acknowledgmentNumber;
    vector<string> flags;
    string payload;
};

struct Route {
    CIDRNetwork network;
    string nextHop;

    Route(CIDRNetwork network, string nextHop)
        : network(std::move(network)),
          nextHop(std::move(nextHop)) {}
};

class Router {
private:
    vector<Route> routingTable;

public:
    void addRoute(const CIDRNetwork& network, const string& nextHop) {
        routingTable.emplace_back(network, nextHop);
    }

    const Route* lookup(const IPv4Address& destination) const {
        const Route* bestRoute = nullptr;

        for (const auto& route : routingTable) {
            if (!route.network.contains(destination)) {
                continue;
            }

            if (bestRoute == nullptr ||
                route.network.prefix() > bestRoute->network.prefix()) {
                bestRoute = &route;
            }
        }

        return bestRoute;
    }

    void showTable() const {
        for (const auto& route : routingTable) {
            cout << left
                 << setw(20) << route.network.toString()
                 << " -> " << route.nextHop << "\n";
        }
    }
};

class EthernetSwitch {
private:
    unordered_map<string, string> macTable;

public:
    void learn(const string& mac, const string& port) {
        macTable[mac] = port;
    }

    string forward(const string& destinationMAC) const {
        auto iterator = macTable.find(destinationMAC);

        if (iterator == macTable.end()) {
            return "FLOOD";
        }

        return iterator->second;
    }

    void showMACTable() const {
        for (const auto& [mac, port] : macTable) {
            cout << left << setw(25) << mac
                 << " -> " << port << "\n";
        }
    }
};

class TransportConnection {
private:
    uint16_t sourcePort;
    uint16_t destinationPort;
    uint32_t nextSequenceNumber;
    bool established;

public:
    TransportConnection(
        uint16_t sourcePort,
        uint16_t destinationPort
    )
        : sourcePort(sourcePort),
          destinationPort(destinationPort),
          nextSequenceNumber(10000),
          established(false) {}

    void establish() {
        cout << "TCP SYN: "
             << sourcePort << " -> "
             << destinationPort << "\n";

        cout << "TCP SYN-ACK: "
             << destinationPort << " -> "
             << sourcePort << "\n";

        cout << "TCP ACK: "
             << sourcePort << " -> "
             << destinationPort << "\n";

        established = true;
    }

    void send(const string& data) {
        if (!established) {
            throw runtime_error(
                "Cannot send application data before TCP establishment."
            );
        }

        cout << "TCP segment seq=" << nextSequenceNumber
             << " payload=" << data << "\n";

        nextSequenceNumber += static_cast<uint32_t>(data.size());
    }
};

class SecurityPolicy {
private:
    map<OSILayer, string> controls;

public:
    SecurityPolicy() {
        controls[OSILayer::Physical] =
            "Physical access control";
        controls[OSILayer::DataLink] =
            "VLAN and 802.1X controls";
        controls[OSILayer::Network] =
            "ACLs and segmentation";
        controls[OSILayer::Transport] =
            "Port and stateful firewall controls";
        controls[OSILayer::Session] =
            "Session timeout and state validation";
        controls[OSILayer::Presentation] =
            "TLS and certificate validation";
        controls[OSILayer::Application] =
            "Authentication, authorization, input validation";
    }

    void display() const {
        for (const auto& [layer, control] : controls) {
            cout << "L" << static_cast<int>(layer)
                 << " " << setw(14) << left << layerName(layer)
                 << " : " << control << "\n";
        }
    }
};

struct DiagnosticEvent {
    OSILayer layer;
    string action;
    string details;
};

class NetworkMonitor {
private:
    vector<DiagnosticEvent> events;

public:
    void record(
        OSILayer layer,
        const string& action,
        const string& details
    ) {
        events.push_back({layer, action, details});
    }

    void display() const {
        for (const auto& event : events) {
            cout << "L"
                 << static_cast<int>(event.layer)
                 << " "
                 << setw(15)
                 << left
                 << layerName(event.layer)
                 << setw(14)
                 << event.action
                 << event.details
                 << "\n";
        }
    }
};

class EnterpriseNetwork {
private:
    EthernetSwitch accessSwitch;
    Router router;
    NetworkMonitor monitor;
    SecurityPolicy securityPolicy;

    const string clientMAC = "AA:BB:CC:DD:EE:01";
    const string gatewayMAC = "AA:BB:CC:DD:EE:FE";

    IPv4Address clientIP = IPv4Address::parse("192.168.10.20");
    IPv4Address gatewayIP = IPv4Address::parse("192.168.10.1");
    IPv4Address serverIP = IPv4Address::parse("10.20.30.50");

public:
    EnterpriseNetwork() {
        /*
         * Layer 2 configuration.
         * The switch learns which MAC addresses appear on which ports.
         */
        accessSwitch.learn(clientMAC, "Access-Port-1");
        accessSwitch.learn(gatewayMAC, "Uplink-Port-24");

        /*
         * Layer 3 routing configuration.
         * Longest-prefix matching will select the most specific route.
         */
        router.addRoute(
            CIDRNetwork(
                IPv4Address::parse("192.168.10.0"),
                24
            ),
            "Local LAN"
        );

        router.addRoute(
            CIDRNetwork(
                IPv4Address::parse("10.20.30.0"),
                24
            ),
            "Application Network"
        );

        router.addRoute(
            CIDRNetwork(
                IPv4Address::parse("0.0.0.0"),
                0
            ),
            "Internet Gateway"
        );
    }

    void printArchitecture() const {
        title("Enterprise Network Architecture");

        cout << "Client\n";
        cout << "  |\n";
        cout << "Access Switch\n";
        cout << "  |\n";
        cout << "Router\n";
        cout << "  |\n";
        cout << "Application Server\n";

        cout << "\nClient IP : " << clientIP.toString() << "\n";
        cout << "Server IP : " << serverIP.toString() << "\n";
    }

    void demonstrateLayer2() {
        title("Layer 2: Switching");

        cout << "MAC table:\n";
        accessSwitch.showMACTable();

        cout << "\nDestination MAC "
             << gatewayMAC
             << " -> "
             << accessSwitch.forward(gatewayMAC)
             << "\n";
    }

    void demonstrateLayer3() {
        title("Layer 3: Routing");

        cout << "Routing table:\n";
        router.showTable();

        const Route* route = router.lookup(serverIP);

        if (route == nullptr) {
            throw runtime_error("No route to application server.");
        }

        cout << "\nDestination "
             << serverIP.toString()
             << " uses "
             << route->network.toString()
             << " -> "
             << route->nextHop
             << "\n";
    }

    void demonstrateLayer4() {
        title("Layer 4: Transport");

        TransportConnection connection(51500, 443);
        connection.establish();
        connection.send("GET /inventory HTTP/1.1");
    }

    void demonstrateEndToEndRequest() {
        title("End-to-End HTTPS Request");

        monitor.record(
            OSILayer::Application,
            "CREATE",
            "Browser creates HTTP request"
        );

        monitor.record(
            OSILayer::Presentation,
            "PROTECT",
            "TLS encrypts application communication"
        );

        monitor.record(
            OSILayer::Session,
            "TRACK",
            "Logical session state is maintained"
        );

        monitor.record(
            OSILayer::Transport,
            "SEGMENT",
            "TCP targets port 443"
        );

        monitor.record(
            OSILayer::Network,
            "ROUTE",
            "IP packet targets application server"
        );

        monitor.record(
            OSILayer::DataLink,
            "FRAME",
            "Ethernet frame targets next hop"
        );

        monitor.record(
            OSILayer::Physical,
            "TRANSMIT",
            "Bits become electrical/optical/radio signals"
        );

        monitor.display();
    }

    void demonstrateTTL() {
        title("Failure Case: TTL Expiration");

        IPPacket packet{
            clientIP,
            serverIP,
            2,
            6,
            "HTTPS"
        };

        cout << "Initial TTL: " << static_cast<int>(packet.ttl) << "\n";

        bool forwarded = packet.forward();
        cout << "After router 1: TTL="
             << static_cast<int>(packet.ttl)
             << ", forwarded="
             << boolalpha
             << forwarded
             << "\n";

        forwarded = packet.forward();
        cout << "After router 2: TTL="
             << static_cast<int>(packet.ttl)
             << ", forwarded="
             << boolalpha
             << forwarded
             << "\n";

        if (!forwarded) {
            cout << "Packet expired; a real router would normally generate "
                    "an ICMP Time Exceeded response.\n";
        }
    }

    void demonstrateSecurity() const {
        title("Security Controls Across Layers");
        securityPolicy.display();
    }

    void demonstrateTroubleshooting() const {
        title("Layer-Oriented Troubleshooting");

        const vector<pair<OSILayer, string>> symptoms = {
            {OSILayer::Physical, "No link or damaged cable"},
            {OSILayer::DataLink, "VLAN or MAC-learning problem"},
            {OSILayer::Network, "Incorrect address or missing route"},
            {OSILayer::Transport, "Port blocked or handshake failure"},
            {OSILayer::Session, "Expired or invalid session state"},
            {OSILayer::Presentation, "TLS/certificate/encoding failure"},
            {OSILayer::Application, "HTTP or application-level error"}
        };

        for (const auto& [layer, symptom] : symptoms) {
            cout << "L"
                 << static_cast<int>(layer)
                 << " "
                 << setw(15)
                 << left
                 << layerName(layer)
                 << ": "
                 << symptom
                 << "\n";
        }
    }
};

void demonstrateOSIReference() {
    title("OSI Seven-Layer Reference");

    for (int i = 1; i <= 7; ++i) {
        OSILayer layer = static_cast<OSILayer>(i);

        cout << "L"
             << i
             << " "
             << setw(15)
             << left
             << layerName(layer)
             << " PDU="
             << pduName(layer)
             << "\n";
    }
}

void demonstrateComplexity() {
    title("Algorithmic Complexity");

    cout << "MAC-table lookup with unordered_map: expected O(1)\n";
    cout << "Route lookup in this demonstration: O(R), where R is route count.\n";
    cout << "Longest-prefix selection scans all candidate routes.\n";
    cout << "Production routers use optimized forwarding structures to reduce lookup cost.\n";
}

void demonstrateTradeoffs() {
    title("Architectural Trade-offs");

    cout << "Layering benefits:\n";
    cout << "  - Separation of concerns\n";
    cout << "  - Interoperability\n";
    cout << "  - Easier diagnostics\n";
    cout << "  - Independent protocol evolution\n";

    cout << "\nLayering trade-offs:\n";
    cout << "  - Additional headers and processing\n";
    cout << "  - Real protocols may span conceptual layers\n";
    cout << "  - Multiple layers may independently implement similar controls\n";
}

void runValidationTests() {
    title("Validation Tests");

    IPv4Address address = IPv4Address::parse("192.168.1.10");

    if (address.toString() != "192.168.1.10") {
        throw runtime_error("IPv4 conversion test failed.");
    }

    CIDRNetwork network(
        IPv4Address::parse("192.168.1.0"),
        24
    );

    if (!network.contains(address)) {
        throw runtime_error("CIDR containment test failed.");
    }

    if (network.contains(IPv4Address::parse("10.0.0.1"))) {
        throw runtime_error("CIDR exclusion test failed.");
    }

    bool exceptionCaught = false;

    try {
        IPv4Address::parse("999.1.1.1");
    } catch (const invalid_argument&) {
        exceptionCaught = true;
    }

    if (!exceptionCaught) {
        throw runtime_error("Invalid IP test failed.");
    }

    cout << "All validation tests passed.\n";
}

int main() {
    try {
        title("OSI MODEL C++ INDUSTRY-STYLE CASE STUDY");

        demonstrateOSIReference();

        EnterpriseNetwork network;

        network.printArchitecture();
        network.demonstrateLayer2();
        network.demonstrateLayer3();
        network.demonstrateLayer4();
        network.demonstrateEndToEndRequest();
        network.demonstrateTTL();
        network.demonstrateSecurity();
        network.demonstrateTroubleshooting();

        demonstrateComplexity();
        demonstrateTradeoffs();
        runValidationTests();

        title("CASE STUDY COMPLETE");
        cout << "Enterprise network simulation completed successfully.\n";

        return 0;
    } catch (const exception& error) {
        cerr << "Fatal error: " << error.what() << "\n";
        return 1;
    }
}
