/*
 * Networking Fundamentals and Wireshark Concepts
 * =================================================
 *
 * C++17 case study:
 *
 * A small enterprise network monitoring and troubleshooting system.
 *
 * The system models:
 *   - Clients and servers
 *   - Ethernet frames
 *   - IPv4 packets
 *   - TCP and UDP
 *   - Ports
 *   - DNS and HTTP
 *   - Routing
 *   - NAT
 *   - Firewall decisions
 *   - Packet capture records
 *   - Wireshark-style filtering
 *   - TCP conversation grouping
 *   - Traffic statistics
 *   - Security observations
 *
 * This program does not capture real traffic. It uses realistic
 * packet records to demonstrate how a packet-analysis application
 * could organize and inspect network observations.
 *
 * Compile:
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic networking_case_study.cpp -o networking_case_study
 */

#include <algorithm>
#include <array>
#include <cstdint>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <numeric>
#include <optional>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

using namespace std;


// ============================================================================
// OUTPUT HELPERS
// ============================================================================

void section(const string& title) {
    cout << "\n" << string(78, '=') << "\n";
    cout << title << "\n";
    cout << string(78, '=') << "\n";
}

void subsection(const string& title) {
    cout << "\n" << string(78, '-') << "\n";
    cout << title << "\n";
    cout << string(78, '-') << "\n";
}


// ============================================================================
// IPv4 ADDRESS
// ============================================================================

class IPv4Address {
private:
    uint32_t value_;

public:
    explicit IPv4Address(uint32_t value = 0)
        : value_(value) {}

    static IPv4Address parse(const string& text) {
        array<unsigned, 4> octets{};
        char separator1 = 0;
        char separator2 = 0;
        char separator3 = 0;

        stringstream stream(text);

        if (!(stream >>
              octets[0] >> separator1 >>
              octets[1] >> separator2 >>
              octets[2] >> separator3 >>
              octets[3])) {
            throw invalid_argument("Invalid IPv4 address: " + text);
        }

        if (separator1 != '.' ||
            separator2 != '.' ||
            separator3 != '.') {
            throw invalid_argument("Invalid IPv4 address: " + text);
        }

        for (unsigned octet : octets) {
            if (octet > 255) {
                throw invalid_argument("IPv4 octet out of range.");
            }
        }

        uint32_t value =
            (octets[0] << 24) |
            (octets[1] << 16) |
            (octets[2] << 8) |
            octets[3];

        return IPv4Address(value);
    }

    uint32_t value() const {
        return value_;
    }

    string toString() const {
        return to_string((value_ >> 24) & 255) + "." +
               to_string((value_ >> 16) & 255) + "." +
               to_string((value_ >> 8) & 255) + "." +
               to_string(value_ & 255);
    }

    bool operator==(const IPv4Address& other) const {
        return value_ == other.value_;
    }

    bool operator<(const IPv4Address& other) const {
        return value_ < other.value_;
    }
};


// ============================================================================
// CIDR NETWORK
// ============================================================================

class IPv4Network {
private:
    IPv4Address network_;
    uint8_t prefixLength_;

public:
    IPv4Network(IPv4Address address, uint8_t prefixLength)
        : prefixLength_(prefixLength) {

        if (prefixLength > 32) {
            throw invalid_argument("Prefix length must be <= 32.");
        }

        uint32_t mask =
            prefixLength == 0
                ? 0
                : 0xFFFFFFFFu << (32 - prefixLength);

        network_ = IPv4Address(address.value() & mask);
    }

    bool contains(const IPv4Address& address) const {
        uint32_t mask =
            prefixLength_ == 0
                ? 0
                : 0xFFFFFFFFu << (32 - prefixLength_);

        return (address.value() & mask) == network_.value();
    }

    uint8_t prefixLength() const {
        return prefixLength_;
    }

    IPv4Address networkAddress() const {
        return network_;
    }

    string toString() const {
        return network_.toString() + "/" +
               to_string(prefixLength_);
    }
};


// ============================================================================
// MAC ADDRESS
// ============================================================================

class MacAddress {
private:
    array<uint8_t, 6> bytes_{};

public:
    MacAddress() = default;

    explicit MacAddress(array<uint8_t, 6> bytes)
        : bytes_(bytes) {}

    static MacAddress parse(const string& text) {
        string cleaned;

        for (char character : text) {
            if (character == ':' || character == '-') {
                continue;
            }

            cleaned += character;
        }

        if (cleaned.size() != 12) {
            throw invalid_argument("Invalid MAC address.");
        }

        array<uint8_t, 6> bytes{};

        for (size_t index = 0; index < 6; ++index) {
            const string byteText =
                cleaned.substr(index * 2, 2);

            unsigned value = 0;
            stringstream stream;
            stream << hex << byteText;
            stream >> value;

            if (value > 255) {
                throw invalid_argument("Invalid MAC byte.");
            }

            bytes[index] =
                static_cast<uint8_t>(value);
        }

        return MacAddress(bytes);
    }

    string toString() const {
        stringstream stream;
        stream << hex << setfill('0');

        for (size_t index = 0; index < bytes_.size(); ++index) {
            if (index != 0) {
                stream << ":";
            }

            stream << setw(2)
                   << static_cast<unsigned>(bytes_[index]);
        }

        return stream.str();
    }

    bool operator==(const MacAddress& other) const {
        return bytes_ == other.bytes_;
    }

    bool operator<(const MacAddress& other) const {
        return bytes_ < other.bytes_;
    }
};


// ============================================================================
// PORT
// ============================================================================

class Port {
private:
    uint16_t value_;

public:
    explicit Port(uint16_t value)
        : value_(value) {}

    uint16_t value() const {
        return value_;
    }

    string description() const {
        static const map<uint16_t, string> knownPorts = {
            {22, "SSH"},
            {25, "SMTP"},
            {53, "DNS"},
            {67, "DHCP server"},
            {68, "DHCP client"},
            {80, "HTTP"},
            {123, "NTP"},
            {161, "SNMP"},
            {443, "HTTPS"},
            {3389, "RDP"}
        };

        auto iterator = knownPorts.find(value_);

        if (iterator != knownPorts.end()) {
            return iterator->second;
        }

        if (value_ <= 1023) {
            return "well-known range";
        }

        if (value_ <= 49151) {
            return "registered range";
        }

        return "dynamic/private range";
    }
};


// ============================================================================
// PROTOCOL TYPES
// ============================================================================

enum class TransportProtocol {
    TCP,
    UDP,
    ICMP
};

string protocolToString(TransportProtocol protocol) {
    switch (protocol) {
        case TransportProtocol::TCP:
            return "TCP";
        case TransportProtocol::UDP:
            return "UDP";
        case TransportProtocol::ICMP:
            return "ICMP";
    }

    return "UNKNOWN";
}


// ============================================================================
// TCP FLAGS
// ============================================================================

enum TcpFlags : uint8_t {
    SYN = 0x02,
    ACK = 0x10,
    FIN = 0x01,
    RST = 0x04,
    PSH = 0x08
};

string tcpFlagsToString(uint8_t flags) {
    vector<string> names;

    if (flags & SYN) {
        names.emplace_back("SYN");
    }

    if (flags & ACK) {
        names.emplace_back("ACK");
    }

    if (flags & FIN) {
        names.emplace_back("FIN");
    }

    if (flags & RST) {
        names.emplace_back("RST");
    }

    if (flags & PSH) {
        names.emplace_back("PSH");
    }

    if (names.empty()) {
        return "NONE";
    }

    string result;

    for (size_t index = 0; index < names.size(); ++index) {
        if (index != 0) {
            result += ", ";
        }

        result += names[index];
    }

    return result;
}


// ============================================================================
// TCP SEGMENT
// ============================================================================

struct TCPSegment {
    Port sourcePort;
    Port destinationPort;
    uint32_t sequenceNumber;
    uint32_t acknowledgementNumber;
    uint8_t flags;
    uint16_t windowSize;
    string payload;

    string describe() const {
        return
            to_string(sourcePort.value()) + " -> " +
            to_string(destinationPort.value()) +
            ", seq=" + to_string(sequenceNumber) +
            ", ack=" + to_string(acknowledgementNumber) +
            ", flags=[" + tcpFlagsToString(flags) + "]" +
            ", window=" + to_string(windowSize) +
            ", payload=" + to_string(payload.size()) +
            " bytes";
    }
};


// ============================================================================
// UDP DATAGRAM
// ============================================================================

struct UDPDatagram {
    Port sourcePort;
    Port destinationPort;
    string payload;

    string describe() const {
        return
            to_string(sourcePort.value()) + " -> " +
            to_string(destinationPort.value()) +
            ", payload=" + to_string(payload.size()) +
            " bytes";
    }
};


// ============================================================================
// ROUTING
// ============================================================================

struct Route {
    IPv4Network destination;
    optional<IPv4Address> nextHop;
    string interfaceName;
    int metric = 0;

    bool matches(const IPv4Address& address) const {
        return destination.contains(address);
    }
};

class RoutingTable {
private:
    vector<Route> routes_;

public:
    explicit RoutingTable(vector<Route> routes)
        : routes_(move(routes)) {}

    optional<Route> lookup(const IPv4Address& destination) const {
        vector<Route> matches;

        for (const Route& route : routes_) {
            if (route.matches(destination)) {
                matches.push_back(route);
            }
        }

        if (matches.empty()) {
            return nullopt;
        }

        /*
         * Routers select the most specific matching prefix.
         *
         * Example:
         *
         *   192.168.1.0/24
         *   0.0.0.0/0
         *
         * Both can technically match 192.168.1.20, but /24 is
         * preferred because it provides a more specific route.
         */
        sort(
            matches.begin(),
            matches.end(),
            [](const Route& left, const Route& right) {
                if (
                    left.destination.prefixLength() !=
                    right.destination.prefixLength()
                ) {
                    return left.destination.prefixLength() >
                           right.destination.prefixLength();
                }

                return left.metric < right.metric;
            }
        );

        return matches.front();
    }
};


// ============================================================================
// NAT
// ============================================================================

struct NATEntry {
    IPv4Address internalIp;
    Port internalPort;
    IPv4Address translatedIp;
    Port translatedPort;
    IPv4Address destinationIp;
    Port destinationPort;
    TransportProtocol protocol;
};


// ============================================================================
// FIREWALL
// ============================================================================

enum class FirewallAction {
    ALLOW,
    DENY
};

struct FirewallRule {
    IPv4Network sourceNetwork;
    optional<uint16_t> destinationPort;
    optional<TransportProtocol> protocol;
    FirewallAction action;
    string description;

    bool matches(
        const IPv4Address& source,
        const Port& destination,
        TransportProtocol packetProtocol
    ) const {
        if (!sourceNetwork.contains(source)) {
            return false;
        }

        if (
            destinationPort.has_value() &&
            destination.value() != destinationPort.value()
        ) {
            return false;
        }

        if (
            protocol.has_value() &&
            protocol.value() != packetProtocol
        ) {
            return false;
        }

        return true;
    }
};

class Firewall {
private:
    vector<FirewallRule> rules_;

public:
    explicit Firewall(vector<FirewallRule> rules)
        : rules_(move(rules)) {}

    pair<FirewallAction, string> evaluate(
        const IPv4Address& source,
        const Port& destination,
        TransportProtocol protocol
    ) const {
        for (const FirewallRule& rule : rules_) {
            if (rule.matches(source, destination, protocol)) {
                return {rule.action, rule.description};
            }
        }

        /*
         * An explicit default deny is safer than accidentally allowing
         * traffic that no policy rule describes.
         */
        return {
            FirewallAction::DENY,
            "Implicit deny"
        };
    }
};


// ============================================================================
// PACKET
// ============================================================================

struct Packet {
    uint64_t number;
    double timestamp;
    MacAddress sourceMac;
    MacAddress destinationMac;
    IPv4Address sourceIp;
    IPv4Address destinationIp;
    TransportProtocol transportProtocol;
    optional<Port> sourcePort;
    optional<Port> destinationPort;
    optional<uint8_t> tcpFlags;
    string payload;
    optional<string> applicationProtocol;
    string info;

    size_t length() const {
        return payload.size();
    }

    string summary() const {
        stringstream output;

        output << setw(3) << number << " "
               << left << setw(5)
               << protocolToString(transportProtocol)
               << " ";

        string endpoints;

        if (sourcePort.has_value()) {
            endpoints =
                sourceIp.toString() + ":" +
                to_string(sourcePort->value()) +
                " -> " +
                destinationIp.toString() + ":" +
                to_string(destinationPort->value());
        } else {
            endpoints =
                sourceIp.toString() +
                " -> " +
                destinationIp.toString();
        }

        output << setw(45) << endpoints
               << " "
               << setw(8)
               << applicationProtocol.value_or("-")
               << " ";

        if (tcpFlags.has_value()) {
            output << setw(20)
                   << ("[" +
                       tcpFlagsToString(tcpFlags.value()) +
                       "]");
        } else {
            output << setw(20) << "";
        }

        output << " len="
               << setw(4)
               << length()
               << " "
               << info;

        return output.str();
    }
};


// ============================================================================
// TCP HANDSHAKE
// ============================================================================

vector<TCPSegment> createTcpHandshake() {
    constexpr uint32_t clientSequence = 1000;
    constexpr uint32_t serverSequence = 5000;

    return {
        {
            Port(53142),
            Port(443),
            clientSequence,
            0,
            SYN,
            64240,
            ""
        },
        {
            Port(443),
            Port(53142),
            serverSequence,
            clientSequence + 1,
            static_cast<uint8_t>(SYN | ACK),
            65535,
            ""
        },
        {
            Port(53142),
            Port(443),
            clientSequence + 1,
            serverSequence + 1,
            ACK,
            64240,
            ""
        }
    };
}


// ============================================================================
// PACKET ANALYZER
// ============================================================================

class PacketAnalyzer {
private:
    const vector<Packet>& packets_;

public:
    explicit PacketAnalyzer(const vector<Packet>& packets)
        : packets_(packets) {}

    map<string, size_t> protocolCounts() const {
        map<string, size_t> result;

        for (const Packet& packet : packets_) {
            ++result[
                protocolToString(packet.transportProtocol)
            ];
        }

        return result;
    }

    map<string, size_t> applicationCounts() const {
        map<string, size_t> result;

        for (const Packet& packet : packets_) {
            if (packet.applicationProtocol.has_value()) {
                ++result[
                    packet.applicationProtocol.value()
                ];
            }
        }

        return result;
    }

    vector<pair<string, size_t>> topTalkers(
        size_t limit
    ) const {
        map<string, size_t> bytes;

        for (const Packet& packet : packets_) {
            bytes[packet.sourceIp.toString()] += packet.length();
            bytes[packet.destinationIp.toString()] += packet.length();
        }

        vector<pair<string, size_t>> entries(
            bytes.begin(),
            bytes.end()
        );

        sort(
            entries.begin(),
            entries.end(),
            [](const auto& left, const auto& right) {
                return left.second > right.second;
            }
        );

        if (entries.size() > limit) {
            entries.resize(limit);
        }

        return entries;
    }

    vector<Packet> filterProtocol(
        TransportProtocol protocol
    ) const {
        vector<Packet> result;

        for (const Packet& packet : packets_) {
            if (packet.transportProtocol == protocol) {
                result.push_back(packet);
            }
        }

        return result;
    }

    vector<Packet> filterPort(uint16_t port) const {
        vector<Packet> result;

        for (const Packet& packet : packets_) {
            if (
                (packet.sourcePort.has_value() &&
                 packet.sourcePort->value() == port) ||
                (packet.destinationPort.has_value() &&
                 packet.destinationPort->value() == port)
            ) {
                result.push_back(packet);
            }
        }

        return result;
    }

    vector<Packet> filterIp(
        const IPv4Address& address
    ) const {
        vector<Packet> result;

        for (const Packet& packet : packets_) {
            if (
                packet.sourceIp == address ||
                packet.destinationIp == address
            ) {
                result.push_back(packet);
            }
        }

        return result;
    }

    vector<Packet> filterApplication(
        const string& protocol
    ) const {
        vector<Packet> result;

        for (const Packet& packet : packets_) {
            if (
                packet.applicationProtocol.has_value() &&
                packet.applicationProtocol.value() == protocol
            ) {
                result.push_back(packet);
            }
        }

        return result;
    }
};


// ============================================================================
// TCP STREAM IDENTIFIER
// ============================================================================

string endpointString(
    const IPv4Address& address,
    const Port& port
) {
    return address.toString() + ":" +
           to_string(port.value());
}

string tcpStreamKey(const Packet& packet) {
    if (
        !packet.sourcePort.has_value() ||
        !packet.destinationPort.has_value()
    ) {
        return "";
    }

    string first = endpointString(
        packet.sourceIp,
        packet.sourcePort.value()
    );

    string second = endpointString(
        packet.destinationIp,
        packet.destinationPort.value()
    );

    if (first > second) {
        swap(first, second);
    }

    return first + " <-> " + second;
}


// ============================================================================
// SIMPLE INTERNET CHECKSUM
// ============================================================================

uint16_t internetChecksum(const vector<uint8_t>& bytes) {
    uint32_t sum = 0;

    for (size_t index = 0; index < bytes.size(); index += 2) {
        uint16_t word =
            static_cast<uint16_t>(bytes[index]) << 8;

        if (index + 1 < bytes.size()) {
            word |= bytes[index + 1];
        }

        sum += word;

        while (sum >> 16) {
            sum =
                (sum & 0xFFFFu) +
                (sum >> 16);
        }
    }

    return static_cast<uint16_t>(~sum);
}


// ============================================================================
// HTTP PARSING
// ============================================================================

struct HttpRequest {
    string method;
    string path;
    string version;
    map<string, string> headers;
};

HttpRequest parseHttpRequest(const string& request) {
    HttpRequest result;

    stringstream stream(request);
    string line;

    if (!getline(stream, line)) {
        throw invalid_argument("HTTP request is empty.");
    }

    if (!line.empty() && line.back() == '\r') {
        line.pop_back();
    }

    stringstream requestLine(line);

    if (
        !(requestLine >>
          result.method >>
          result.path >>
          result.version)
    ) {
        throw invalid_argument("Invalid HTTP request line.");
    }

    while (getline(stream, line)) {
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }

        if (line.empty()) {
            break;
        }

        const size_t separator = line.find(':');

        if (separator == string::npos) {
            continue;
        }

        string name = line.substr(0, separator);
        string value = line.substr(separator + 1);

        while (!value.empty() && value.front() == ' ') {
            value.erase(value.begin());
        }

        result.headers[name] = value;
    }

    return result;
}


// ============================================================================
// MAIN CASE STUDY
// ============================================================================

int main() {
    try {
        section("C++ NETWORK MONITORING AND TROUBLESHOOTING CASE STUDY");

        cout << R"(
Scenario:

A small enterprise LAN contains client machines, a gateway router,
an application server and external services.

A monitoring component has collected packet metadata. The engineering
team wants to determine:

  1. Which hosts communicated?
  2. Which protocols and ports were used?
  3. How was the TCP connection established?
  4. Which route would the gateway select?
  5. Which traffic would the firewall permit?
  6. Which packets belong to the same TCP conversation?
  7. What information could be observed in a packet capture?
)";


        // --------------------------------------------------------------------
        // NETWORK TOPOLOGY
        // --------------------------------------------------------------------

        section("NETWORK TOPOLOGY");

        const IPv4Address clientIp =
            IPv4Address::parse("192.168.1.25");

        const IPv4Address gatewayIp =
            IPv4Address::parse("192.168.1.1");

        const IPv4Address webServerIp =
            IPv4Address::parse("93.184.216.34");

        const IPv4Address dnsServerIp =
            IPv4Address::parse("8.8.8.8");

        const IPv4Network lan(
            IPv4Address::parse("192.168.1.0"),
            24
        );

        cout << "Client       : " << clientIp.toString() << "\n";
        cout << "Gateway      : " << gatewayIp.toString() << "\n";
        cout << "Web server   : " << webServerIp.toString() << "\n";
        cout << "DNS server   : " << dnsServerIp.toString() << "\n";
        cout << "LAN          : " << lan.toString() << "\n";


        // --------------------------------------------------------------------
        // MAC ADDRESSING
        // --------------------------------------------------------------------

        section("ETHERNET AND MAC ADDRESSING");

        const MacAddress clientMac =
            MacAddress::parse("00:11:22:33:44:55");

        const MacAddress gatewayMac =
            MacAddress::parse("aa:aa:aa:aa:aa:01");

        const MacAddress serverMac =
            MacAddress::parse("aa:bb:cc:dd:ee:ff");

        cout << "Client MAC : " << clientMac.toString() << "\n";
        cout << "Gateway MAC: " << gatewayMac.toString() << "\n";
        cout << "Server MAC : " << serverMac.toString() << "\n";


        // --------------------------------------------------------------------
        // PORTS
        // --------------------------------------------------------------------

        section("PORTS");

        Port httpsPort(443);
        Port dnsPort(53);
        Port clientPort(53142);

        cout << "HTTPS port : "
             << httpsPort.value()
             << " (" << httpsPort.description() << ")\n";

        cout << "DNS port   : "
             << dnsPort.value()
             << " (" << dnsPort.description() << ")\n";

        cout << "Client port: "
             << clientPort.value()
             << " (" << clientPort.description() << ")\n";


        // --------------------------------------------------------------------
        // TCP HANDSHAKE
        // --------------------------------------------------------------------

        section("TCP THREE-WAY HANDSHAKE");

        const vector<TCPSegment> handshake =
            createTcpHandshake();

        for (size_t index = 0; index < handshake.size(); ++index) {
            cout << index + 1
                 << ". "
                 << handshake[index].describe()
                 << "\n";
        }

        cout << R"(
The first segment contains SYN.

The second segment contains SYN + ACK.

The third segment contains ACK.

This establishes the basic TCP connection state before ordinary
application data is exchanged.
)";


        // --------------------------------------------------------------------
        // APPLICATION DATA
        // --------------------------------------------------------------------

        section("HTTP APPLICATION DATA");

        const string httpPayload =
            "GET /index.html HTTP/1.1\r\n"
            "Host: example.test\r\n"
            "Accept: text/html\r\n"
            "Connection: close\r\n"
            "\r\n";

        cout << httpPayload;


        // --------------------------------------------------------------------
        // PACKET CAPTURE
        // --------------------------------------------------------------------

        section("SIMULATED PACKET CAPTURE");

        vector<Packet> packets;

        packets.push_back({
            1,
            0.000,
            clientMac,
            serverMac,
            clientIp,
            webServerIp,
            TransportProtocol::TCP,
            Port(53142),
            Port(443),
            SYN,
            "",
            nullopt,
            "SYN"
        });

        packets.push_back({
            2,
            0.001,
            serverMac,
            clientMac,
            webServerIp,
            clientIp,
            TransportProtocol::TCP,
            Port(443),
            Port(53142),
            static_cast<uint8_t>(SYN | ACK),
            "",
            nullopt,
            "SYN, ACK"
        });

        packets.push_back({
            3,
            0.002,
            clientMac,
            serverMac,
            clientIp,
            webServerIp,
            TransportProtocol::TCP,
            Port(53142),
            Port(443),
            ACK,
            "",
            nullopt,
            "ACK"
        });

        packets.push_back({
            4,
            0.005,
            clientMac,
            serverMac,
            clientIp,
            webServerIp,
            TransportProtocol::TCP,
            Port(53142),
            Port(443),
            static_cast<uint8_t>(ACK | PSH),
            httpPayload,
            string("HTTP"),
            "HTTP GET /index.html"
        });

        packets.push_back({
            5,
            0.030,
            clientMac,
            gatewayMac,
            clientIp,
            dnsServerIp,
            TransportProtocol::UDP,
            Port(53000),
            Port(53),
            nullopt,
            "example.test",
            string("DNS"),
            "DNS query"
        });

        packets.push_back({
            6,
            0.040,
            clientMac,
            gatewayMac,
            clientIp,
            IPv4Address::parse("1.1.1.1"),
            TransportProtocol::ICMP,
            nullopt,
            nullopt,
            nullopt,
            "ping",
            string("ICMP"),
            "Echo request"
        });

        cout << "No. Proto Source/Destination"
             << "                                       "
             << "App      Flags                Length Info\n";

        cout << string(120, '-') << "\n";

        for (const Packet& packet : packets) {
            cout << packet.summary() << "\n";
        }


        // --------------------------------------------------------------------
        // ANALYZER
        // --------------------------------------------------------------------

        section("PACKET ANALYSIS");

        PacketAnalyzer analyzer(packets);

        cout << "Transport protocol distribution:\n";

        for (const auto& [protocol, count] :
             analyzer.protocolCounts()) {
            cout << "  " << protocol
                 << ": " << count << "\n";
        }

        cout << "\nApplication protocol distribution:\n";

        for (const auto& [protocol, count] :
             analyzer.applicationCounts()) {
            cout << "  " << protocol
                 << ": " << count << "\n";
        }


        // --------------------------------------------------------------------
        // FILTERING
        // --------------------------------------------------------------------

        section("WIRESHARK-STYLE FILTERING");

        cout << "TCP packets:\n";

        for (const Packet& packet :
             analyzer.filterProtocol(
                 TransportProtocol::TCP
             )) {
            cout << "  " << packet.summary() << "\n";
        }

        cout << "\nPackets involving TCP/443:\n";

        for (const Packet& packet :
             analyzer.filterPort(443)) {
            cout << "  " << packet.summary() << "\n";
        }

        cout << "\nPackets involving client IP:\n";

        for (const Packet& packet :
             analyzer.filterIp(clientIp)) {
            cout << "  " << packet.summary() << "\n";
        }

        cout << "\nDNS application packets:\n";

        for (const Packet& packet :
             analyzer.filterApplication("DNS")) {
            cout << "  " << packet.summary() << "\n";
        }


        // --------------------------------------------------------------------
        // ROUTING TABLE
        // --------------------------------------------------------------------

        section("ROUTING TABLE");

        RoutingTable routingTable({
            {
                IPv4Network(
                    IPv4Address::parse("192.168.1.0"),
                    24
                ),
                nullopt,
                "LAN",
                0
            },
            {
                IPv4Network(
                    IPv4Address::parse("10.0.0.0"),
                    8
                ),
                IPv4Address::parse("10.10.10.1"),
                "WAN1",
                10
            },
            {
                IPv4Network(
                    IPv4Address::parse("0.0.0.0"),
                    0
                ),
                gatewayIp,
                "LAN",
                100
            }
        });

        vector<IPv4Address> routingTests = {
            clientIp,
            IPv4Address::parse("10.20.30.40"),
            webServerIp,
            dnsServerIp
        };

        for (const IPv4Address& destination :
             routingTests) {
            const auto route =
                routingTable.lookup(destination);

            cout << destination.toString() << " -> ";

            if (!route.has_value()) {
                cout << "NO ROUTE\n";
                continue;
            }

            cout << route->destination.toString()
                 << " via ";

            if (route->nextHop.has_value()) {
                cout << route->nextHop->toString();
            } else {
                cout << "direct";
            }

            cout << " on "
                 << route->interfaceName
                 << "\n";
        }


        // --------------------------------------------------------------------
        // FIREWALL
        // --------------------------------------------------------------------

        section("FIREWALL DECISIONS");

        Firewall firewall({
            {
                IPv4Network(
                    IPv4Address::parse("192.168.1.0"),
                    24
                ),
                443,
                TransportProtocol::TCP,
                FirewallAction::ALLOW,
                "Allow HTTPS from LAN"
            },
            {
                IPv4Network(
                    IPv4Address::parse("192.168.1.0"),
                    24
                ),
                22,
                TransportProtocol::TCP,
                FirewallAction::DENY,
                "Block SSH from LAN"
            }
        });

        struct FirewallTest {
            IPv4Address source;
            uint16_t destinationPort;
            TransportProtocol protocol;
        };

        vector<FirewallTest> firewallTests = {
            {clientIp, 443, TransportProtocol::TCP},
            {clientIp, 22, TransportProtocol::TCP},
            {clientIp, 53, TransportProtocol::UDP}
        };

        for (const FirewallTest& test : firewallTests) {
            auto result = firewall.evaluate(
                test.source,
                Port(test.destinationPort),
                test.protocol
            );

            cout << test.source.toString()
                 << " -> "
                 << protocolToString(test.protocol)
                 << "/"
                 << test.destinationPort
                 << ": ";

            cout << (
                result.first == FirewallAction::ALLOW
                    ? "ALLOW"
                    : "DENY"
            );

            cout << " (" << result.second << ")\n";
        }


        // --------------------------------------------------------------------
        // NAT
        // --------------------------------------------------------------------

        section("NAT TRANSLATION");

        NATEntry nat{
            clientIp,
            Port(53142),
            IPv4Address::parse("203.0.113.20"),
            Port(42001),
            webServerIp,
            Port(443),
            TransportProtocol::TCP
        };

        cout << "Inside local : "
             << nat.internalIp.toString()
             << ":" << nat.internalPort.value()
             << "\n";

        cout << "Inside global: "
             << nat.translatedIp.toString()
             << ":" << nat.translatedPort.value()
             << "\n";

        cout << "Destination  : "
             << nat.destinationIp.toString()
             << ":" << nat.destinationPort.value()
             << "\n";


        // --------------------------------------------------------------------
        // TCP STREAMS
        // --------------------------------------------------------------------

        section("TCP CONVERSATION GROUPING");

        map<string, vector<Packet>> streams;

        for (const Packet& packet : packets) {
            if (
                packet.transportProtocol !=
                TransportProtocol::TCP
            ) {
                continue;
            }

            const string key =
                tcpStreamKey(packet);

            streams[key].push_back(packet);
        }

        for (const auto& [stream, streamPackets] : streams) {
            cout << "\nStream: " << stream << "\n";

            for (const Packet& packet : streamPackets) {
                cout << "  #"
                     << packet.number
                     << " "
                     << packet.info
                     << "\n";
            }
        }


        // --------------------------------------------------------------------
        // LATENCY
        // --------------------------------------------------------------------

        section("PACKET TIMING");

        for (size_t index = 1; index < packets.size(); ++index) {
            const double delay =
                packets[index].timestamp -
                packets[index - 1].timestamp;

            cout << "Between packet "
                 << packets[index - 1].number
                 << " and "
                 << packets[index].number
                 << ": "
                 << fixed
                 << setprecision(3)
                 << delay * 1000
                 << " ms\n";
        }


        // --------------------------------------------------------------------
        // HTTP DISSECTION
        // --------------------------------------------------------------------

        section("HTTP DISSECTION");

        const HttpRequest request =
            parseHttpRequest(httpPayload);

        cout << "Method : " << request.method << "\n";
        cout << "Path   : " << request.path << "\n";
        cout << "Version: " << request.version << "\n";

        cout << "Headers:\n";

        for (const auto& [name, value] :
             request.headers) {
            cout << "  " << name
                 << ": "
                 << value
                 << "\n";
        }


        // --------------------------------------------------------------------
        // CHECKSUM
        // --------------------------------------------------------------------

        section("INTERNET CHECKSUM");

        vector<uint8_t> checksumInput = {
            0x6e, 0x65, 0x74, 0x77,
            0x6f, 0x72, 0x6b
        };

        const uint16_t checksum =
            internetChecksum(checksumInput);

        cout << "Checksum: 0x"
             << hex
             << setw(4)
             << setfill('0')
             << checksum
             << dec
             << setfill(' ')
             << "\n";


        // --------------------------------------------------------------------
        // MTU
        // --------------------------------------------------------------------

        section("MTU AND PACKET SIZE");

        constexpr size_t ipv4HeaderSize = 20;
        constexpr size_t mtu = 1500;

        vector<size_t> payloadSizes = {
            100,
            1400,
            1480,
            1500,
            2000
        };

        for (size_t payloadSize : payloadSizes) {
            const bool oversized =
                payloadSize + ipv4HeaderSize > mtu;

            cout << "Payload "
                 << setw(4)
                 << payloadSize
                 << " bytes -> "
                 << (
                    oversized
                        ? "requires oversize handling"
                        : "fits within simplified MTU"
                 )
                 << "\n";
        }


        // --------------------------------------------------------------------
        // PACKET LOSS
        // --------------------------------------------------------------------

        section("PACKET LOSS SIMULATION");

        mt19937 generator(7);
        bernoulli_distribution loss(0.20);

        vector<int> delivered;
        vector<int> lost;

        for (int sequence = 1; sequence <= 20; ++sequence) {
            if (loss(generator)) {
                lost.push_back(sequence);
            } else {
                delivered.push_back(sequence);
            }
        }

        cout << "Delivered: ";

        for (int value : delivered) {
            cout << value << " ";
        }

        cout << "\nLost: ";

        for (int value : lost) {
            cout << value << " ";
        }

        cout << "\nDelivery ratio: "
             << fixed
             << setprecision(1)
             << static_cast<double>(delivered.size()) /
                    20.0 *
                    100.0
             << "%\n";


        // --------------------------------------------------------------------
        // TOP TALKERS
        // --------------------------------------------------------------------

        section("TOP TALKERS");

        for (const auto& [address, bytes] :
             analyzer.topTalkers(5)) {
            cout << setw(16)
                 << left
                 << address
                 << right
                 << " "
                 << bytes
                 << " bytes\n";
        }


        // --------------------------------------------------------------------
        // WIRESHARK FILTER REFERENCE
        // --------------------------------------------------------------------

        section("WIRESHARK CONCEPT REFERENCE");

        const vector<pair<string, string>> filters = {
            {"tcp", "Display TCP packets."},
            {"udp", "Display UDP packets."},
            {"dns", "Display DNS packets."},
            {"http", "Display HTTP packets."},
            {"icmp", "Display ICMP packets."},
            {"ip.addr == 192.168.1.25",
             "Match either IP endpoint."},
            {"ip.src == 192.168.1.25",
             "Match source IP."},
            {"ip.dst == 8.8.8.8",
             "Match destination IP."},
            {"tcp.port == 443",
             "Match TCP port 443."},
            {"tcp.flags.syn == 1",
             "Match packets with SYN set."},
            {"tcp.flags.reset == 1",
             "Match TCP reset packets."},
            {"tcp.stream == 0",
             "Select one TCP conversation."}
        };

        for (const auto& [expression, meaning] : filters) {
            cout << left
                 << setw(35)
                 << expression
                 << " -> "
                 << meaning
                 << "\n";
        }


        // --------------------------------------------------------------------
        // TROUBLESHOOTING
        // --------------------------------------------------------------------

        section("TROUBLESHOOTING DECISION MODEL");

        const vector<string> troubleshootingSteps = {
            "Check physical or wireless connectivity.",
            "Check IP address and subnet.",
            "Check default gateway.",
            "Check local reachability.",
            "Check DNS resolution.",
            "Check routing.",
            "Check transport ports.",
            "Check application protocol.",
            "Check firewall and access-control rules.",
            "Inspect timing, retransmissions and resets."
        };

        for (size_t index = 0;
             index < troubleshootingSteps.size();
             ++index) {
            cout << index + 1
                 << ". "
                 << troubleshootingSteps[index]
                 << "\n";
        }


        // --------------------------------------------------------------------
        // SECURITY OBSERVATIONS
        // --------------------------------------------------------------------

        section("SECURITY OBSERVATIONS");

        cout << R"(
A packet capture is potentially sensitive.

Depending on the protocol and encryption state, it can expose:

  - IP addresses
  - MAC addresses
  - Ports
  - Hostnames
  - Timing and traffic patterns
  - Application metadata
  - Unencrypted application content
  - Authentication information transmitted without protection

Encryption such as TLS protects application payloads in transit, but
network metadata can remain observable.

Capture files should be stored and shared according to the organization's
security and privacy requirements.
)";


        // --------------------------------------------------------------------
        // SELF TESTS
        // --------------------------------------------------------------------

        section("SELF-TESTS");

        if (
            IPv4Address::parse("192.168.1.10").toString() !=
            "192.168.1.10"
        ) {
            throw runtime_error("IPv4 conversion test failed.");
        }

        if (
            IPv4Network(
                IPv4Address::parse("192.168.1.0"),
                24
            ).contains(
                IPv4Address::parse("192.168.1.25")
            ) == false
        ) {
            throw runtime_error("Subnet containment test failed.");
        }

        if (
            IPv4Network(
                IPv4Address::parse("192.168.1.0"),
                24
            ).contains(
                IPv4Address::parse("192.168.2.25")
            )
        ) {
            throw runtime_error("Subnet boundary test failed.");
        }

        if (
            httpsPort.description() !=
            "HTTPS"
        ) {
            throw runtime_error("Port test failed.");
        }

        if (
            handshake.size() != 3 ||
            !(handshake[0].flags & SYN) ||
            !(handshake[1].flags & SYN) ||
            !(handshake[1].flags & ACK) ||
            !(handshake[2].flags & ACK)
        ) {
            throw runtime_error("TCP handshake test failed.");
        }

        if (
            firewall.evaluate(
                clientIp,
                Port(443),
                TransportProtocol::TCP
            ).first != FirewallAction::ALLOW
        ) {
            throw runtime_error("Firewall allow test failed.");
        }

        if (
            firewall.evaluate(
                clientIp,
                Port(22),
                TransportProtocol::TCP
            ).first != FirewallAction::DENY
        ) {
            throw runtime_error("Firewall deny test failed.");
        }

        if (
            analyzer.filterProtocol(
                TransportProtocol::TCP
            ).size() != 4
        ) {
            throw runtime_error("TCP filtering test failed.");
        }

        if (
            analyzer.filterPort(443).size() != 4
        ) {
            throw runtime_error("Port filtering test failed.");
        }

        if (
            request.method != "GET" ||
            request.path != "/index.html"
        ) {
            throw runtime_error("HTTP parsing test failed.");
        }

        cout << "All self-tests passed.\n";


        // --------------------------------------------------------------------
        // FINAL MODEL
        // --------------------------------------------------------------------

        section("SYSTEM MODEL");

        cout << R"(
Client application
        |
        | Application protocol
        v
TCP / UDP
        |
        | Source port + destination port
        v
IPv4 / IPv6
        |
        | Source IP + destination IP
        v
Ethernet / Wi-Fi
        |
        | MAC addresses
        v
Physical network

A packet analyzer observes the resulting traffic and exposes fields
that correspond to these layers.

The most useful analysis connects individual packet fields with:

  - addressing
  - routing
  - transport state
  - application behavior
  - timing
  - reliability
  - security
  - network architecture
)";

        return 0;
    }
    catch (const exception& error) {
        cerr << "\nFatal error: "
             << error.what()
             << "\n";

        return 1;
    }
}
