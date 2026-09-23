/*
 * TCP/IP MODEL
 * ============
 *
 * Comprehensive C++17 case study.
 *
 * Scenario:
 * ---------
 * A small enterprise network contains client machines, an internal
 * application server and an Internet gateway. A client wants to request
 * an HTTPS resource from an external server.
 *
 * The program models:
 *
 *   Application
 *       |
 *   TCP transport
 *       |
 *   IPv4 routing
 *       |
 *   Ethernet frame
 *       |
 *   Gateway / NAT
 *       |
 *   Internet
 *
 * It also demonstrates:
 *
 * - Layer and protocol mapping
 * - IPv4 addresses
 * - CIDR subnetting
 * - Longest-prefix routing
 * - TCP three-way handshake
 * - TCP sequence and acknowledgment numbers
 * - UDP
 * - Ports
 * - DNS
 * - HTTP
 * - NAT
 * - MTU fragmentation
 * - Internet checksum
 * - Error handling
 * - Complexity considerations
 * - Security and performance considerations
 *
 * Compile:
 *
 *     g++ -std=c++17 -O2 tcp_ip_model.cpp -o tcp_ip_model
 *
 * Run:
 *
 *     ./tcp_ip_model
 */

#include <algorithm>
#include <array>
#include <cstdint>
#include <exception>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <optional>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

using namespace std;

// ---------------------------------------------------------------------------
// 1. TCP/IP LAYERS
// ---------------------------------------------------------------------------

enum class Layer {
    NetworkAccess = 1,
    Internet = 2,
    Transport = 3,
    Application = 4
};

string layerName(Layer layer) {
    switch (layer) {
        case Layer::NetworkAccess:
            return "Network Access";
        case Layer::Internet:
            return "Internet";
        case Layer::Transport:
            return "Transport";
        case Layer::Application:
            return "Application";
    }

    return "Unknown";
}

enum class Protocol {
    Ethernet,
    ARP,
    IPv4,
    IPv6,
    ICMP,
    TCP,
    UDP,
    DNS,
    HTTP,
    HTTPS,
    DHCP
};

string protocolName(Protocol protocol) {
    switch (protocol) {
        case Protocol::Ethernet: return "Ethernet";
        case Protocol::ARP: return "ARP";
        case Protocol::IPv4: return "IPv4";
        case Protocol::IPv6: return "IPv6";
        case Protocol::ICMP: return "ICMP";
        case Protocol::TCP: return "TCP";
        case Protocol::UDP: return "UDP";
        case Protocol::DNS: return "DNS";
        case Protocol::HTTP: return "HTTP";
        case Protocol::HTTPS: return "HTTPS";
        case Protocol::DHCP: return "DHCP";
    }

    return "Unknown";
}

Layer protocolLayer(Protocol protocol) {
    switch (protocol) {
        case Protocol::Ethernet:
        case Protocol::ARP:
            return Layer::NetworkAccess;

        case Protocol::IPv4:
        case Protocol::IPv6:
        case Protocol::ICMP:
            return Layer::Internet;

        case Protocol::TCP:
        case Protocol::UDP:
            return Layer::Transport;

        case Protocol::DNS:
        case Protocol::HTTP:
        case Protocol::HTTPS:
        case Protocol::DHCP:
            return Layer::Application;
    }

    throw runtime_error("Unknown protocol");
}

void demonstrateProtocolMapping() {
    cout << "\nPROTOCOL MAPPING\n";
    cout << string(72, '-') << '\n';

    const vector<Protocol> protocols = {
        Protocol::Ethernet,
        Protocol::ARP,
        Protocol::IPv4,
        Protocol::IPv6,
        Protocol::ICMP,
        Protocol::TCP,
        Protocol::UDP,
        Protocol::DNS,
        Protocol::HTTP,
        Protocol::HTTPS,
        Protocol::DHCP
    };

    for (Protocol protocol : protocols) {
        cout << left
             << setw(12) << protocolName(protocol)
             << " -> "
             << layerName(protocolLayer(protocol))
             << '\n';
    }
}

// ---------------------------------------------------------------------------
// 2. IPV4 ADDRESS REPRESENTATION
// ---------------------------------------------------------------------------

class IPv4Address {
private:
    uint32_t value_;

public:
    explicit IPv4Address(uint32_t value = 0)
        : value_(value) {}

    static IPv4Address parse(const string& text) {
        stringstream stream(text);
        string token;
        array<int, 4> octets{};
        int index = 0;

        while (getline(stream, token, '.')) {
            if (index >= 4 || token.empty()) {
                throw invalid_argument("Invalid IPv4 address: " + text);
            }

            for (char character : token) {
                if (!isdigit(static_cast<unsigned char>(character))) {
                    throw invalid_argument(
                        "Invalid IPv4 address: " + text
                    );
                }
            }

            int number = stoi(token);

            if (number < 0 || number > 255) {
                throw invalid_argument(
                    "IPv4 octet outside 0-255: " + text
                );
            }

            octets[index++] = number;
        }

        if (index != 4) {
            throw invalid_argument("Invalid IPv4 address: " + text);
        }

        uint32_t value =
            (static_cast<uint32_t>(octets[0]) << 24) |
            (static_cast<uint32_t>(octets[1]) << 16) |
            (static_cast<uint32_t>(octets[2]) << 8) |
            static_cast<uint32_t>(octets[3]);

        return IPv4Address(value);
    }

    uint32_t value() const {
        return value_;
    }

    string toString() const {
        ostringstream output;

        output
            << ((value_ >> 24) & 0xFF) << '.'
            << ((value_ >> 16) & 0xFF) << '.'
            << ((value_ >> 8) & 0xFF) << '.'
            << (value_ & 0xFF);

        return output.str();
    }

    bool isPrivate() const {
        const uint8_t first = (value_ >> 24) & 0xFF;
        const uint8_t second = (value_ >> 16) & 0xFF;

        return
            first == 10 ||
            (first == 172 && second >= 16 && second <= 31) ||
            (first == 192 && second == 168);
    }

    bool operator==(const IPv4Address& other) const {
        return value_ == other.value_;
    }
};

// ---------------------------------------------------------------------------
// 3. CIDR NETWORK
// ---------------------------------------------------------------------------

class IPv4Network {
private:
    IPv4Address networkAddress_;
    uint8_t prefixLength_;

    uint32_t mask() const {
        if (prefixLength_ == 0) {
            return 0;
        }

        return 0xFFFFFFFFu << (32 - prefixLength_);
    }

public:
    IPv4Network(
        const IPv4Address& address,
        uint8_t prefixLength
    )
        : prefixLength_(prefixLength) {
        if (prefixLength > 32) {
            throw invalid_argument("IPv4 prefix must be <= 32");
        }

        uint32_t network =
            address.value() & mask();

        networkAddress_ = IPv4Address(network);
    }

    bool contains(const IPv4Address& address) const {
        return (address.value() & mask()) ==
               networkAddress_.value();
    }

    uint8_t prefixLength() const {
        return prefixLength_;
    }

    IPv4Address networkAddress() const {
        return networkAddress_;
    }

    IPv4Address broadcastAddress() const {
        uint32_t broadcast =
            networkAddress_.value() | ~mask();

        return IPv4Address(broadcast);
    }

    uint64_t addressCount() const {
        if (prefixLength_ == 32) {
            return 1;
        }

        return uint64_t{1} << (32 - prefixLength_);
    }

    string toString() const {
        return networkAddress_.toString() +
               "/" +
               to_string(prefixLength_);
    }
};

void demonstrateSubnetting() {
    cout << "\nSUBNETTING\n";
    cout << string(72, '-') << '\n';

    vector<pair<string, uint8_t>> examples = {
        {"192.168.1.10", 24},
        {"192.168.1.70", 26},
        {"10.10.10.4", 30}
    };

    for (const auto& [address, prefix] : examples) {
        IPv4Network network(
            IPv4Address::parse(address),
            prefix
        );

        cout << network.toString()
             << " | network="
             << network.networkAddress().toString()
             << " | broadcast="
             << network.broadcastAddress().toString()
             << " | addresses="
             << network.addressCount()
             << '\n';
    }
}

// ---------------------------------------------------------------------------
// 4. ROUTING TABLE
// ---------------------------------------------------------------------------

struct Route {
    IPv4Network network;
    IPv4Address nextHop;
    string interfaceName;

    Route(
        IPv4Network networkValue,
        IPv4Address nextHopValue,
        string interfaceValue
    )
        : network(std::move(networkValue)),
          nextHop(nextHopValue),
          interfaceName(std::move(interfaceValue)) {}
};

class RoutingTable {
private:
    vector<Route> routes_;

public:
    void addRoute(
        const string& networkAddress,
        uint8_t prefix,
        const string& nextHop,
        const string& interfaceName
    ) {
        routes_.emplace_back(
            IPv4Network(
                IPv4Address::parse(networkAddress),
                prefix
            ),
            IPv4Address::parse(nextHop),
            interfaceName
        );
    }

    const Route* lookup(
        const IPv4Address& destination
    ) const {
        const Route* best = nullptr;

        for (const Route& route : routes_) {
            if (!route.network.contains(destination)) {
                continue;
            }

            if (
                best == nullptr ||
                route.network.prefixLength() >
                best->network.prefixLength()
            ) {
                best = &route;
            }
        }

        return best;
    }
};

void demonstrateRouting() {
    cout << "\nROUTING TABLE\n";
    cout << string(72, '-') << '\n';

    RoutingTable table;

    table.addRoute(
        "0.0.0.0",
        0,
        "192.168.1.1",
        "eth0"
    );

    table.addRoute(
        "10.0.0.0",
        8,
        "192.168.1.254",
        "eth1"
    );

    table.addRoute(
        "10.10.0.0",
        16,
        "192.168.1.253",
        "eth2"
    );

    table.addRoute(
        "10.10.20.0",
        24,
        "192.168.1.252",
        "eth3"
    );

    for (const string& destinationText : {
        string("8.8.8.8"),
        string("10.20.1.5"),
        string("10.10.5.10"),
        string("10.10.20.42")
    }) {
        IPv4Address destination =
            IPv4Address::parse(destinationText);

        const Route* route = table.lookup(destination);

        if (route == nullptr) {
            cout << destinationText
                 << " -> no route\n";
        } else {
            cout << destinationText
                 << " -> "
                 << route->network.toString()
                 << " -> next hop "
                 << route->nextHop.toString()
                 << " via "
                 << route->interfaceName
                 << '\n';
        }
    }

    /*
     * Complexity:
     *
     * A simple vector table performs O(R) lookup where R is the number
     * of routes. Production routers use specialized structures and
     * hardware acceleration to make lookups much faster at scale.
     */
}

// ---------------------------------------------------------------------------
// 5. TCP ENDPOINT AND THREE-WAY HANDSHAKE
// ---------------------------------------------------------------------------

enum class TCPState {
    Closed,
    Listen,
    SynSent,
    SynReceived,
    Established
};

string tcpStateName(TCPState state) {
    switch (state) {
        case TCPState::Closed: return "CLOSED";
        case TCPState::Listen: return "LISTEN";
        case TCPState::SynSent: return "SYN-SENT";
        case TCPState::SynReceived: return "SYN-RECEIVED";
        case TCPState::Established: return "ESTABLISHED";
    }

    return "UNKNOWN";
}

class TCPEndpoint {
private:
    string name_;
    TCPState state_;
    uint32_t sequenceNumber_;
    uint32_t acknowledgmentNumber_;

public:
    explicit TCPEndpoint(string name)
        : name_(std::move(name)),
          state_(TCPState::Closed),
          sequenceNumber_(0),
          acknowledgmentNumber_(0) {}

    void listen() {
        if (state_ != TCPState::Closed) {
            throw logic_error(
                "Endpoint can only enter LISTEN from CLOSED"
            );
        }

        state_ = TCPState::Listen;
    }

    void sendSyn() {
        if (state_ != TCPState::Closed) {
            throw logic_error(
                "SYN requires CLOSED state"
            );
        }

        sequenceNumber_ = 1000;
        state_ = TCPState::SynSent;
    }

    void receiveSyn(uint32_t peerSequence) {
        if (state_ != TCPState::Listen) {
            throw logic_error(
                "Server is not listening"
            );
        }

        acknowledgmentNumber_ = peerSequence + 1;
        sequenceNumber_ = 5000;
        state_ = TCPState::SynReceived;
    }

    void receiveSynAck(uint32_t peerSequence) {
        if (state_ != TCPState::SynSent) {
            throw logic_error(
                "Unexpected SYN-ACK"
            );
        }

        acknowledgmentNumber_ = peerSequence + 1;
        state_ = TCPState::Established;
    }

    void receiveAck() {
        if (state_ != TCPState::SynReceived) {
            throw logic_error(
                "Unexpected ACK"
            );
        }

        state_ = TCPState::Established;
    }

    TCPState state() const {
        return state_;
    }

    uint32_t sequenceNumber() const {
        return sequenceNumber_;
    }
};

void demonstrateTCPHandshake() {
    cout << "\nTCP THREE-WAY HANDSHAKE\n";
    cout << string(72, '-') << '\n';

    TCPEndpoint client("client");
    TCPEndpoint server("server");

    server.listen();
    client.sendSyn();

    cout << "1. Client sends SYN: "
         << tcpStateName(client.state())
         << '\n';

    server.receiveSyn(client.sequenceNumber());

    cout << "2. Server sends SYN-ACK: "
         << tcpStateName(server.state())
         << '\n';

    client.receiveSynAck(5000);

    cout << "3. Client sends ACK: "
         << tcpStateName(client.state())
         << '\n';

    server.receiveAck();

    cout << "Client state: "
         << tcpStateName(client.state())
         << '\n';

    cout << "Server state: "
         << tcpStateName(server.state())
         << '\n';
}

// ---------------------------------------------------------------------------
// 6. UDP DATAGRAM
// ---------------------------------------------------------------------------

class UDPDatagram {
private:
    uint16_t sourcePort_;
    uint16_t destinationPort_;
    string payload_;

public:
    UDPDatagram(
        uint16_t sourcePort,
        uint16_t destinationPort,
        string payload
    )
        : sourcePort_(sourcePort),
          destinationPort_(destinationPort),
          payload_(std::move(payload)) {}

    uint16_t length() const {
        return static_cast<uint16_t>(
            8 + payload_.size()
        );
    }

    void print() const {
        cout << "UDP "
             << sourcePort_
             << " -> "
             << destinationPort_
             << ", length="
             << length()
             << ", payload=\""
             << payload_
             << "\"\n";
    }
};

void demonstrateUDP() {
    cout << "\nUDP\n";
    cout << string(72, '-') << '\n';

    UDPDatagram datagram(
        50000,
        53,
        "DNS query payload"
    );

    datagram.print();

    cout
        << "UDP does not provide TCP-style connection establishment, "
        << "ordering and retransmission.\n";
}

// ---------------------------------------------------------------------------
// 7. PORTS
// ---------------------------------------------------------------------------

map<uint16_t, string> commonPorts = {
    {22, "SSH"},
    {25, "SMTP"},
    {53, "DNS"},
    {67, "DHCP server"},
    {68, "DHCP client"},
    {80, "HTTP"},
    {110, "POP3"},
    {123, "NTP"},
    {143, "IMAP"},
    {443, "HTTPS"},
    {3306, "MySQL"},
    {5432, "PostgreSQL"},
    {6379, "Redis"}
};

void demonstratePorts() {
    cout << "\nTRANSPORT PORTS\n";
    cout << string(72, '-') << '\n';

    for (uint16_t port : {
        uint16_t(22),
        uint16_t(53),
        uint16_t(80),
        uint16_t(443),
        uint16_t(5432),
        uint16_t(9999)
    }) {
        auto iterator = commonPorts.find(port);

        cout << port
             << " -> "
             << (
                 iterator == commonPorts.end()
                     ? "No common mapping"
                     : iterator->second
             )
             << '\n';
    }
}

// ---------------------------------------------------------------------------
// 8. DNS CACHE
// ---------------------------------------------------------------------------

struct DNSRecord {
    string name;
    string type;
    string value;
    uint64_t ttlSeconds;
};

class DNSCache {
private:
    map<pair<string, string>, DNSRecord> records_;

public:
    void put(const DNSRecord& record) {
        records_[{
            record.name,
            record.type
        }] = record;
    }

    optional<DNSRecord> get(
        const string& name,
        const string& type
    ) const {
        auto iterator =
            records_.find({name, type});

        if (iterator == records_.end()) {
            return nullopt;
        }

        return iterator->second;
    }
};

void demonstrateDNS() {
    cout << "\nDNS\n";
    cout << string(72, '-') << '\n';

    DNSCache cache;

    cache.put({
        "example.com",
        "A",
        "93.184.216.34",
        300
    });

    optional<DNSRecord> record =
        cache.get("example.com", "A");

    if (record.has_value()) {
        cout << record->name
             << " "
             << record->type
             << " "
             << record->value
             << " TTL="
             << record->ttlSeconds
             << '\n';
    }

    cout
        << "DNS converts names into records such as A, AAAA, MX, "
        << "CNAME, NS and TXT.\n";
}

// ---------------------------------------------------------------------------
// 9. HTTP APPLICATION LAYER
// ---------------------------------------------------------------------------

class HTTPRequest {
private:
    string method_;
    string target_;
    map<string, string> headers_;
    string body_;

public:
    HTTPRequest(
        string method,
        string target,
        map<string, string> headers,
        string body = ""
    )
        : method_(std::move(method)),
          target_(std::move(target)),
          headers_(std::move(headers)),
          body_(std::move(body)) {}

    string serialize() const {
        ostringstream output;

        output
            << method_
            << ' '
            << target_
            << " HTTP/1.1\r\n";

        for (const auto& [name, value] : headers_) {
            output
                << name
                << ": "
                << value
                << "\r\n";
        }

        output
            << "\r\n"
            << body_;

        return output.str();
    }
};

void demonstrateHTTP() {
    cout << "\nHTTP\n";
    cout << string(72, '-') << '\n';

    HTTPRequest request(
        "GET",
        "/products",
        {
            {"Host", "example.com"},
            {"Accept", "application/json"},
            {"Connection", "close"}
        }
    );

    cout << request.serialize() << '\n';
}

// ---------------------------------------------------------------------------
// 10. INTERNET CHECKSUM
// ---------------------------------------------------------------------------

uint16_t internetChecksum(
    const vector<uint8_t>& data
) {
    uint32_t sum = 0;

    size_t index = 0;

    while (index + 1 < data.size()) {
        uint16_t word =
            static_cast<uint16_t>(
                (static_cast<uint16_t>(data[index]) << 8) |
                data[index + 1]
            );

        sum += word;

        while (sum > 0xFFFF) {
            sum =
                (sum & 0xFFFF) +
                (sum >> 16);
        }

        index += 2;
    }

    if (index < data.size()) {
        uint16_t word =
            static_cast<uint16_t>(
                data[index] << 8
            );

        sum += word;

        while (sum > 0xFFFF) {
            sum =
                (sum & 0xFFFF) +
                (sum >> 16);
        }
    }

    return static_cast<uint16_t>(
        ~sum
    );
}

void demonstrateChecksum() {
    cout << "\nINTERNET CHECKSUM\n";
    cout << string(72, '-') << '\n';

    string message =
        "TCP/IP checksum demonstration";

    vector<uint8_t> bytes(
        message.begin(),
        message.end()
    );

    uint16_t checksum =
        internetChecksum(bytes);

    cout
        << "Checksum: 0x"
        << hex
        << setw(4)
        << setfill('0')
        << checksum
        << dec
        << setfill(' ')
        << '\n';
}

// ---------------------------------------------------------------------------
// 11. NAT
// ---------------------------------------------------------------------------

struct NATMapping {
    IPv4Address privateAddress;
    uint16_t privatePort;
    IPv4Address publicAddress;
    uint16_t publicPort;
    IPv4Address destinationAddress;
    uint16_t destinationPort;
};

class NATTable {
private:
    IPv4Address publicAddress_;
    uint16_t nextPort_;
    vector<NATMapping> mappings_;

public:
    explicit NATTable(
        IPv4Address publicAddress
    )
        : publicAddress_(publicAddress),
          nextPort_(40000) {}

    NATMapping translate(
        IPv4Address privateAddress,
        uint16_t privatePort,
        IPv4Address destinationAddress,
        uint16_t destinationPort
    ) {
        for (const NATMapping& mapping : mappings_) {
            if (
                mapping.privateAddress == privateAddress &&
                mapping.privatePort == privatePort &&
                mapping.destinationAddress == destinationAddress &&
                mapping.destinationPort == destinationPort
            ) {
                return mapping;
            }
        }

        NATMapping mapping{
            privateAddress,
            privatePort,
            publicAddress_,
            nextPort_++,
            destinationAddress,
            destinationPort
        };

        mappings_.push_back(mapping);

        return mapping;
    }
};

void demonstrateNAT() {
    cout << "\nNAT\n";
    cout << string(72, '-') << '\n';

    NATTable nat(
        IPv4Address::parse("203.0.113.10")
    );

    NATMapping mapping =
        nat.translate(
            IPv4Address::parse("192.168.1.20"),
            51000,
            IPv4Address::parse("93.184.216.34"),
            443
        );

    cout
        << mapping.privateAddress.toString()
        << ':'
        << mapping.privatePort
        << " -> "
        << mapping.publicAddress.toString()
        << ':'
        << mapping.publicPort
        << '\n';
}

// ---------------------------------------------------------------------------
// 12. MTU FRAGMENTATION
// ---------------------------------------------------------------------------

vector<vector<uint8_t>> fragmentPayload(
    const vector<uint8_t>& payload,
    size_t mtu,
    size_t ipHeaderSize = 20
) {
    if (mtu <= ipHeaderSize) {
        throw invalid_argument(
            "MTU must exceed IP header size"
        );
    }

    size_t maximumPayload =
        ((mtu - ipHeaderSize) / 8) * 8;

    if (maximumPayload == 0) {
        throw invalid_argument(
            "No valid fragment payload"
        );
    }

    vector<vector<uint8_t>> fragments;

    for (
        size_t offset = 0;
        offset < payload.size();
        offset += maximumPayload
    ) {
        size_t end =
            min(
                offset + maximumPayload,
                payload.size()
            );

        fragments.emplace_back(
            payload.begin() + offset,
            payload.begin() + end
        );
    }

    return fragments;
}

void demonstrateMTU() {
    cout << "\nMTU AND FRAGMENTATION\n";
    cout << string(72, '-') << '\n';

    vector<uint8_t> payload(100, 0xAB);

    vector<vector<uint8_t>> fragments =
        fragmentPayload(
            payload,
            44,
            20
        );

    cout
        << "Original payload: "
        << payload.size()
        << " bytes\n";

    cout << "Fragment sizes: ";

    for (const auto& fragment : fragments) {
        cout << fragment.size() << ' ';
    }

    cout << '\n';

    cout
        << "IPv4 fragmentation uses offsets based on 8-byte units. "
        << "Avoiding unnecessary fragmentation can improve efficiency.\n";
}

// ---------------------------------------------------------------------------
// 13. ENTERPRISE CASE STUDY
// ---------------------------------------------------------------------------

struct ApplicationMessage {
    string method;
    string resource;
    string host;
    string body;
};

struct TCPConnection {
    uint16_t sourcePort;
    uint16_t destinationPort;
    uint32_t sequenceNumber;
    uint32_t acknowledgmentNumber;
};

struct IPPacket {
    IPv4Address source;
    IPv4Address destination;
    uint8_t ttl;
    TCPConnection transport;
    ApplicationMessage application;
};

struct EthernetFrame {
    string sourceMAC;
    string destinationMAC;
    IPPacket packet;
};

class EnterpriseClient {
private:
    IPv4Address address_;
    IPv4Address gateway_;
    uint16_t ephemeralPort_;

public:
    EnterpriseClient(
        IPv4Address address,
        IPv4Address gateway,
        uint16_t ephemeralPort
    )
        : address_(address),
          gateway_(gateway),
          ephemeralPort_(ephemeralPort) {}

    EthernetFrame buildHTTPSRequest(
        const IPv4Address& destination
    ) const {
        ApplicationMessage application{
            "GET",
            "/api/products",
            "example.com",
            ""
        };

        TCPConnection tcp{
            ephemeralPort_,
            443,
            1000,
            0
        };

        IPPacket packet{
            address_,
            destination,
            64,
            tcp,
            application
        };

        return EthernetFrame{
            "02:00:00:00:10:01",
            "02:00:00:00:00:01",
            packet
        };
    }

    IPv4Address address() const {
        return address_;
    }

    IPv4Address gateway() const {
        return gateway_;
    }
};

class EnterpriseGateway {
private:
    IPv4Address internalAddress_;
    IPv4Address publicAddress_;
    NATTable nat_;

public:
    EnterpriseGateway(
        IPv4Address internalAddress,
        IPv4Address publicAddress
    )
        : internalAddress_(internalAddress),
          publicAddress_(publicAddress),
          nat_(publicAddress) {}

    void process(
        const EthernetFrame& frame
    ) {
        const IPPacket& packet =
            frame.packet;

        cout << "\nGATEWAY PROCESSING\n";
        cout << string(72, '-') << '\n';

        cout
            << "Received frame from MAC "
            << frame.sourceMAC
            << '\n';

        cout
            << "IP source: "
            << packet.source.toString()
            << '\n';

        cout
            << "IP destination: "
            << packet.destination.toString()
            << '\n';

        cout
            << "TCP source port: "
            << packet.transport.sourcePort
            << '\n';

        cout
            << "TCP destination port: "
            << packet.transport.destinationPort
            << '\n';

        cout
            << "Application request: "
            << packet.application.method
            << ' '
            << packet.application.resource
            << '\n';

        NATMapping mapping =
            nat_.translate(
                packet.source,
                packet.transport.sourcePort,
                packet.destination,
                packet.transport.destinationPort
            );

        cout
            << "NAT translation: "
            << mapping.privateAddress.toString()
            << ':'
            << mapping.privatePort
            << " -> "
            << mapping.publicAddress.toString()
            << ':'
            << mapping.publicPort
            << '\n';

        /*
         * A real gateway would update packet fields, recompute relevant
         * checksums, consult its routing table and transmit the packet
         * through the appropriate external interface.
         */
    }
};

void runEnterpriseCaseStudy() {
    cout << "\nENTERPRISE HTTPS REQUEST CASE STUDY\n";
    cout << string(72, '=') << '\n';

    IPv4Address clientIP =
        IPv4Address::parse("192.168.1.20");

    IPv4Address gatewayIP =
        IPv4Address::parse("192.168.1.1");

    IPv4Address publicIP =
        IPv4Address::parse("203.0.113.10");

    IPv4Address webServerIP =
        IPv4Address::parse("93.184.216.34");

    EnterpriseClient client(
        clientIP,
        gatewayIP,
        51000
    );

    EnterpriseGateway gateway(
        gatewayIP,
        publicIP
    );

    EthernetFrame frame =
        client.buildHTTPSRequest(
            webServerIP
        );

    cout
        << "Client "
        << client.address().toString()
        << " wants HTTPS access to "
        << webServerIP.toString()
        << ":443\n";

    cout
        << "\nLayer-by-layer construction:\n";

    cout
        << "Application: "
        << frame.packet.application.method
        << ' '
        << frame.packet.application.resource
        << '\n';

    cout
        << "Transport: TCP "
        << frame.packet.transport.sourcePort
        << " -> "
        << frame.packet.transport.destinationPort
        << '\n';

    cout
        << "Internet: "
        << frame.packet.source.toString()
        << " -> "
        << frame.packet.destination.toString()
        << '\n';

    cout
        << "Network Access: Ethernet "
        << frame.sourceMAC
        << " -> "
        << frame.destinationMAC
        << '\n';

    gateway.process(frame);

    cout
        << "\nThe gateway represents the point where private addressing, "
        << "routing and NAT can interact with the Internet-facing network.\n";
}

// ---------------------------------------------------------------------------
// 14. SECURITY AND PERFORMANCE
// ---------------------------------------------------------------------------

void demonstrateSecurityAndPerformance() {
    cout << "\nSECURITY AND PERFORMANCE\n";
    cout << string(72, '-') << '\n';

    cout
        << "Network Access: secure Wi-Fi, VLAN segmentation and switch controls.\n";

    cout
        << "Internet: routing filters, ACLs, network segmentation and IP controls.\n";

    cout
        << "Transport: minimize exposed ports and validate connection attempts.\n";

    cout
        << "Application: TLS, authentication, authorization and input validation.\n";

    cout
        << "Performance: monitor bandwidth, latency, jitter, loss, RTT and MTU.\n";

    cout
        << "Trade-off: stronger security controls can introduce processing, "
        << "configuration or operational overhead.\n";
}

// ---------------------------------------------------------------------------
// 15. TROUBLESHOOTING
// ---------------------------------------------------------------------------

void demonstrateTroubleshooting() {
    cout << "\nTROUBLESHOOTING WORKFLOW\n";
    cout << string(72, '-') << '\n';

    const vector<string> checks = {
        "Check physical or wireless connectivity.",
        "Check interface and MAC-level configuration.",
        "Check IPv4/IPv6 address and subnet.",
        "Check default gateway.",
        "Check routing table.",
        "Test gateway reachability.",
        "Test remote IP connectivity.",
        "Test DNS resolution separately.",
        "Test the destination transport port.",
        "Inspect application protocol responses.",
        "Use packet captures to locate the failing layer."
    };

    for (size_t index = 0; index < checks.size(); ++index) {
        cout
            << index + 1
            << ". "
            << checks[index]
            << '\n';
    }
}

// ---------------------------------------------------------------------------
// 16. MAIN
// ---------------------------------------------------------------------------

int main() {
    try {
        cout << string(72, '=') << '\n';
        cout << "TCP/IP MODEL: C++17 TECHNICAL CASE STUDY\n";
        cout << string(72, '=') << '\n';

        demonstrateProtocolMapping();
        demonstrateSubnetting();
        demonstrateRouting();
        demonstrateTCPHandshake();
        demonstrateUDP();
        demonstratePorts();
        demonstrateDNS();
        demonstrateHTTP();
        demonstrateChecksum();
        demonstrateNAT();
        demonstrateMTU();
        runEnterpriseCaseStudy();
        demonstrateSecurityAndPerformance();
        demonstrateTroubleshooting();

        cout << "\nCASE STUDY COMPLETE\n";

        cout
            << "The modeled communication path is:\n"
            << "Application -> Transport -> Internet -> Network Access\n"
            << "and the receiving side processes those layers in reverse.\n";

        return 0;
    }
    catch (const exception& error) {
        cerr
            << "Fatal error: "
            << error.what()
            << '\n';

        return 1;
    }
}
