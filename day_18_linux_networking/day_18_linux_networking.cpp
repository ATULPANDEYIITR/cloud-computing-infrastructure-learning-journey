#include <arpa/inet.h>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <map>
#include <netdb.h>
#include <netinet/in.h>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/socket.h>
#include <sys/types.h>
#include <thread>
#include <unistd.h>
#include <vector>

/*
 * Linux Networking C++ Case Study
 *
 * Scenario:
 *   A small network diagnostics and service-validation component for an
 *   internal application platform.
 *
 * The program demonstrates:
 *   - IPv4 validation and subnet membership
 *   - routing-table selection through longest-prefix matching
 *   - DNS resolution
 *   - TCP server/client communication
 *   - UDP datagrams
 *   - port validation
 *   - socket inspection concepts
 *   - Linux commands ip, ping, ss, and netstat
 *   - error handling and resource management
 *
 * Compile on Linux:
 *
 *   g++ -std=c++17 -Wall -Wextra -pedantic linux_networking.cpp -o linux_networking
 *
 * Run:
 *
 *   ./linux_networking
 *
 * The program does not modify the host's routing table or interfaces.
 */

namespace netstudy {

// ---------------------------------------------------------------------------
// General utility
// ---------------------------------------------------------------------------

void section(const std::string& title) {
    std::cout << "\n" << std::string(78, '=') << "\n";
    std::cout << title << "\n";
    std::cout << std::string(78, '=') << "\n";
}

void subsection(const std::string& title) {
    std::cout << "\n--- " << title << " ---\n";
}

std::string ipv4ToString(std::uint32_t address) {
    std::ostringstream output;

    output
        << ((address >> 24) & 0xff) << "."
        << ((address >> 16) & 0xff) << "."
        << ((address >> 8) & 0xff) << "."
        << (address & 0xff);

    return output.str();
}

std::uint32_t ipv4FromString(const std::string& address) {
    in_addr parsed{};

    if (inet_pton(AF_INET, address.c_str(), &parsed) != 1) {
        throw std::invalid_argument("Invalid IPv4 address: " + address);
    }

    return ntohl(parsed.s_addr);
}

std::uint32_t prefixMask(int prefixLength) {
    if (prefixLength < 0 || prefixLength > 32) {
        throw std::invalid_argument("IPv4 prefix must be 0..32.");
    }

    if (prefixLength == 0) {
        return 0;
    }

    return 0xffffffffu << (32 - prefixLength);
}

bool addressInNetwork(
    std::uint32_t address,
    std::uint32_t network,
    int prefixLength
) {
    const std::uint32_t mask = prefixMask(prefixLength);

    return (address & mask) == (network & mask);
}

bool validPort(int port) {
    return port >= 0 && port <= 65535;
}


// ---------------------------------------------------------------------------
// IP addressing
// ---------------------------------------------------------------------------

struct IPv4Network {
    std::uint32_t network;
    int prefixLength;

    bool contains(std::uint32_t address) const {
        return addressInNetwork(address, network, prefixLength);
    }

    std::string toString() const {
        return ipv4ToString(network) + "/" +
               std::to_string(prefixLength);
    }
};

void demonstrateIpAddressing() {
    section("1. IPv4 addressing and subnetting");

    const std::vector<std::pair<std::string, int>> examples = {
        {"192.168.1.25", 24},
        {"10.20.30.40", 16},
        {"172.16.10.50", 20},
        {"127.0.0.1", 8},
        {"8.8.8.8", 32},
    };

    for (const auto& [addressText, prefix] : examples) {
        try {
            const auto address = ipv4FromString(addressText);
            const auto mask = prefixMask(prefix);
            const auto network = address & mask;
            const auto broadcast = network | ~mask;

            std::cout
                << std::left
                << std::setw(18) << addressText
                << " /" << std::setw(2) << prefix
                << " network=" << std::setw(15)
                << ipv4ToString(network)
                << " broadcast=" << ipv4ToString(broadcast)
                << "\n";
        } catch (const std::exception& error) {
            std::cout << addressText << ": " << error.what() << "\n";
        }
    }

    subsection("Subnet membership");

    const IPv4Network network{
        ipv4FromString("192.168.50.0"),
        24
    };

    for (const std::string& addressText : {
        "192.168.50.1",
        "192.168.50.200",
        "192.168.51.1"
    }) {
        const auto address = ipv4FromString(addressText);

        std::cout
            << addressText
            << " in "
            << network.toString()
            << " = "
            << std::boolalpha
            << network.contains(address)
            << "\n";
    }
}


// ---------------------------------------------------------------------------
// Routing table model
// ---------------------------------------------------------------------------

struct Route {
    IPv4Network destination;
    std::string interfaceName;
    std::optional<std::string> gateway;
    int metric;
};

class RoutingTable {
private:
    std::vector<Route> routes_;

public:
    explicit RoutingTable(std::vector<Route> routes)
        : routes_(std::move(routes)) {}

    const Route* lookup(const std::string& destinationText) const {
        const auto destination = ipv4FromString(destinationText);

        const Route* best = nullptr;

        for (const auto& route : routes_) {
            if (!route.destination.contains(destination)) {
                continue;
            }

            if (best == nullptr) {
                best = &route;
                continue;
            }

            /*
             * Longest-prefix matching is the fundamental routing rule used
             * here. A /24 is more specific than a /16, which is more specific
             * than a /8. Metric breaks ties between routes with equal prefix
             * length in this simplified model.
             */
            if (
                route.destination.prefixLength >
                    best->destination.prefixLength ||
                (
                    route.destination.prefixLength ==
                        best->destination.prefixLength &&
                    route.metric < best->metric
                )
            ) {
                best = &route;
            }
        }

        return best;
    }

    void print() const {
        for (const auto& route : routes_) {
            std::cout
                << std::left
                << std::setw(18) << route.destination.toString()
                << " dev "
                << std::setw(8) << route.interfaceName
                << " gateway=";

            if (route.gateway.has_value()) {
                std::cout << *route.gateway;
            } else {
                std::cout << "direct";
            }

            std::cout
                << " metric=" << route.metric
                << "\n";
        }
    }
};

void demonstrateRouting() {
    section("2. Routing-table case study");

    /*
     * This is an application-level simulation of routing logic. It does not
     * replace the Linux kernel's real routing table.
     */
    RoutingTable table({
        {
            {ipv4FromString("0.0.0.0"), 0},
            "eth0",
            "192.168.1.1",
            100
        },
        {
            {ipv4FromString("10.0.0.0"), 8},
            "vpn0",
            std::nullopt,
            100
        },
        {
            {ipv4FromString("10.20.0.0"), 16},
            "vpn1",
            std::nullopt,
            100
        },
        {
            {ipv4FromString("10.20.30.0"), 24},
            "vpn2",
            std::nullopt,
            10
        }
    });

    subsection("Modeled routing table");
    table.print();

    subsection("Route decisions");

    for (const std::string& destination : {
        "8.8.8.8",
        "10.5.1.1",
        "10.20.8.9",
        "10.20.30.55"
    }) {
        try {
            const Route* route = table.lookup(destination);

            if (route == nullptr) {
                std::cout << destination << " -> no route\n";
                continue;
            }

            std::cout
                << destination
                << " -> "
                << route->destination.toString()
                << " dev "
                << route->interfaceName
                << " gateway=";

            if (route->gateway.has_value()) {
                std::cout << *route->gateway;
            } else {
                std::cout << "direct";
            }

            std::cout << "\n";
        } catch (const std::exception& error) {
            std::cout << destination << ": " << error.what() << "\n";
        }
    }
}


// ---------------------------------------------------------------------------
// DNS
// ---------------------------------------------------------------------------

struct ResolvedAddress {
    int family;
    std::string numericAddress;
};

std::vector<ResolvedAddress> resolveHostname(
    const std::string& hostname
) {
    addrinfo hints{};
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;

    addrinfo* results = nullptr;

    const int status = getaddrinfo(
        hostname.c_str(),
        nullptr,
        &hints,
        &results
    );

    if (status != 0) {
        throw std::runtime_error(
            "getaddrinfo failed: " +
            std::string(gai_strerror(status))
        );
    }

    std::vector<ResolvedAddress> addresses;

    for (addrinfo* current = results;
         current != nullptr;
         current = current->ai_next) {

        char buffer[INET6_ADDRSTRLEN]{};

        if (current->ai_family == AF_INET) {
            const auto* address =
                reinterpret_cast<const sockaddr_in*>(current->ai_addr);

            inet_ntop(
                AF_INET,
                &address->sin_addr,
                buffer,
                sizeof(buffer)
            );
        } else if (current->ai_family == AF_INET6) {
            const auto* address =
                reinterpret_cast<const sockaddr_in6*>(current->ai_addr);

            inet_ntop(
                AF_INET6,
                &address->sin6_addr,
                buffer,
                sizeof(buffer)
            );
        } else {
            continue;
        }

        addresses.push_back({
            current->ai_family,
            buffer
        });
    }

    freeaddrinfo(results);

    return addresses;
}

void demonstrateDns() {
    section("3. DNS resolution");

    for (const std::string& hostname : {
        "localhost",
        "example.com",
        "invalid.invalid"
    }) {
        try {
            const auto addresses = resolveHostname(hostname);

            std::set<std::string> uniqueAddresses;

            for (const auto& address : addresses) {
                uniqueAddresses.insert(address.numericAddress);
            }

            std::cout << hostname << " -> ";

            if (uniqueAddresses.empty()) {
                std::cout << "no addresses";
            } else {
                bool first = true;

                for (const auto& address : uniqueAddresses) {
                    if (!first) {
                        std::cout << ", ";
                    }

                    std::cout << address;
                    first = false;
                }
            }

            std::cout << "\n";
        } catch (const std::exception& error) {
            std::cout
                << hostname
                << " -> "
                << error.what()
                << "\n";
        }
    }

    std::cout << R"(
DNS concepts:
  A       IPv4 address record
  AAAA    IPv6 address record
  CNAME   Alias
  MX      Mail exchange
  NS      Name server
  TXT     Text data
  PTR     Reverse lookup record
)";
}


// ---------------------------------------------------------------------------
// Socket resource wrapper
// ---------------------------------------------------------------------------

class SocketHandle {
private:
    int descriptor_ = -1;

public:
    SocketHandle() = default;

    explicit SocketHandle(int descriptor)
        : descriptor_(descriptor) {}

    ~SocketHandle() {
        close();
    }

    SocketHandle(const SocketHandle&) = delete;
    SocketHandle& operator=(const SocketHandle&) = delete;

    SocketHandle(SocketHandle&& other) noexcept
        : descriptor_(other.descriptor_) {
        other.descriptor_ = -1;
    }

    SocketHandle& operator=(SocketHandle&& other) noexcept {
        if (this != &other) {
            close();
            descriptor_ = other.descriptor_;
            other.descriptor_ = -1;
        }

        return *this;
    }

    int get() const {
        return descriptor_;
    }

    bool valid() const {
        return descriptor_ >= 0;
    }

    void reset(int descriptor = -1) {
        close();
        descriptor_ = descriptor;
    }

    void close() {
        if (descriptor_ >= 0) {
            ::close(descriptor_);
            descriptor_ = -1;
        }
    }
};


// ---------------------------------------------------------------------------
// TCP server
// ---------------------------------------------------------------------------

class TcpEchoServer {
private:
    SocketHandle serverSocket_;
    int port_ = 0;

public:
    void start() {
        int descriptor = socket(AF_INET, SOCK_STREAM, 0);

        if (descriptor < 0) {
            throw std::runtime_error(
                "socket() failed: " + std::string(std::strerror(errno))
            );
        }

        serverSocket_.reset(descriptor);

        int reuse = 1;

        if (setsockopt(
            serverSocket_.get(),
            SOL_SOCKET,
            SO_REUSEADDR,
            &reuse,
            sizeof(reuse)
        ) < 0) {
            throw std::runtime_error(
                "setsockopt() failed: " +
                std::string(std::strerror(errno))
            );
        }

        sockaddr_in address{};
        address.sin_family = AF_INET;

        /*
         * Loopback binding keeps this educational service inaccessible through
         * ordinary external network interfaces.
         */
        address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);

        /*
         * Port 0 asks the kernel to choose an available ephemeral port.
         */
        address.sin_port = htons(0);

        if (bind(
            serverSocket_.get(),
            reinterpret_cast<const sockaddr*>(&address),
            sizeof(address)
        ) < 0) {
            throw std::runtime_error(
                "bind() failed: " + std::string(std::strerror(errno))
            );
        }

        if (listen(serverSocket_.get(), 8) < 0) {
            throw std::runtime_error(
                "listen() failed: " + std::string(std::strerror(errno))
            );
        }

        sockaddr_in actualAddress{};
        socklen_t length = sizeof(actualAddress);

        if (getsockname(
            serverSocket_.get(),
            reinterpret_cast<sockaddr*>(&actualAddress),
            &length
        ) < 0) {
            throw std::runtime_error(
                "getsockname() failed: " +
                std::string(std::strerror(errno))
            );
        }

        port_ = ntohs(actualAddress.sin_port);
    }

    int port() const {
        return port_;
    }

    void handleOneClient() {
        sockaddr_in clientAddress{};
        socklen_t clientLength = sizeof(clientAddress);

        SocketHandle client(
            accept(
                serverSocket_.get(),
                reinterpret_cast<sockaddr*>(&clientAddress),
                &clientLength
            )
        );

        if (!client.valid()) {
            throw std::runtime_error(
                "accept() failed: " +
                std::string(std::strerror(errno))
            );
        }

        char clientIp[INET_ADDRSTRLEN]{};

        inet_ntop(
            AF_INET,
            &clientAddress.sin_addr,
            clientIp,
            sizeof(clientIp)
        );

        std::cout
            << "Accepted TCP client "
            << clientIp
            << ":"
            << ntohs(clientAddress.sin_port)
            << "\n";

        char buffer[4096]{};

        const ssize_t received = recv(
            client.get(),
            buffer,
            sizeof(buffer),
            0
        );

        if (received < 0) {
            throw std::runtime_error(
                "recv() failed: " +
                std::string(std::strerror(errno))
            );
        }

        if (received == 0) {
            std::cout << "Client closed the connection without data.\n";
            return;
        }

        std::string message(buffer, buffer + received);

        std::cout
            << "Server received: "
            << message
            << "\n";

        const std::string response = "ACK:" + message;

        std::size_t totalSent = 0;

        while (totalSent < response.size()) {
            const ssize_t sent = send(
                client.get(),
                response.data() + totalSent,
                response.size() - totalSent,
                0
            );

            if (sent <= 0) {
                throw std::runtime_error(
                    "send() failed: " +
                    std::string(std::strerror(errno))
                );
            }

            totalSent += static_cast<std::size_t>(sent);
        }
    }
};

void runTcpCaseStudy() {
    section("4. TCP service case study");

    TcpEchoServer server;

    try {
        server.start();

        std::cout
            << "TCP server listening on "
            << "127.0.0.1:"
            << server.port()
            << "\n";

        /*
         * The server accepts exactly one client. The client runs in a separate
         * thread so that both sides can demonstrate the normal TCP lifecycle.
         */
        std::thread serverThread([&server]() {
            try {
                server.handleOneClient();
            } catch (const std::exception& error) {
                std::cerr
                    << "Server thread error: "
                    << error.what()
                    << "\n";
            }
        });

        std::this_thread::sleep_for(
            std::chrono::milliseconds(100)
        );

        SocketHandle client(
            socket(AF_INET, SOCK_STREAM, 0)
        );

        if (!client.valid()) {
            throw std::runtime_error(
                "Client socket() failed: " +
                std::string(std::strerror(errno))
            );
        }

        sockaddr_in destination{};
        destination.sin_family = AF_INET;
        destination.sin_port = htons(
            static_cast<std::uint16_t>(server.port())
        );

        inet_pton(
            AF_INET,
            "127.0.0.1",
            &destination.sin_addr
        );

        if (connect(
            client.get(),
            reinterpret_cast<const sockaddr*>(&destination),
            sizeof(destination)
        ) < 0) {
            throw std::runtime_error(
                "connect() failed: " +
                std::string(std::strerror(errno))
            );
        }

        const std::string message = "hello-linux";

        const ssize_t sent = send(
            client.get(),
            message.data(),
            message.size(),
            0
        );

        if (sent != static_cast<ssize_t>(message.size())) {
            throw std::runtime_error(
                "TCP client did not send the complete message."
            );
        }

        char buffer[4096]{};

        const ssize_t received = recv(
            client.get(),
            buffer,
            sizeof(buffer),
            0
        );

        if (received < 0) {
            throw std::runtime_error(
                "Client recv() failed: " +
                std::string(std::strerror(errno))
            );
        }

        std::cout
            << "Client received: "
            << std::string(buffer, buffer + received)
            << "\n";

        if (serverThread.joinable()) {
            serverThread.join();
        }
    } catch (const std::exception& error) {
        std::cerr
            << "TCP case study failed: "
            << error.what()
            << "\n";
    }
}


// ---------------------------------------------------------------------------
// UDP
// ---------------------------------------------------------------------------

void runUdpCaseStudy() {
    section("5. UDP datagram case study");

    SocketHandle server(socket(AF_INET, SOCK_DGRAM, 0));

    if (!server.valid()) {
        std::cerr
            << "UDP server socket failed: "
            << std::strerror(errno)
            << "\n";
        return;
    }

    sockaddr_in serverAddress{};
    serverAddress.sin_family = AF_INET;
    serverAddress.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    serverAddress.sin_port = htons(0);

    if (bind(
        server.get(),
        reinterpret_cast<const sockaddr*>(&serverAddress),
        sizeof(serverAddress)
    ) < 0) {
        std::cerr
            << "UDP bind failed: "
            << std::strerror(errno)
            << "\n";
        return;
    }

    socklen_t addressLength = sizeof(serverAddress);

    if (getsockname(
        server.get(),
        reinterpret_cast<sockaddr*>(&serverAddress),
        &addressLength
    ) < 0) {
        std::cerr
            << "UDP getsockname failed: "
            << std::strerror(errno)
            << "\n";
        return;
    }

    const int port = ntohs(serverAddress.sin_port);

    std::cout
        << "UDP server listening on 127.0.0.1:"
        << port
        << "\n";

    SocketHandle client(socket(AF_INET, SOCK_DGRAM, 0));

    if (!client.valid()) {
        std::cerr
            << "UDP client socket failed: "
            << std::strerror(errno)
            << "\n";
        return;
    }

    const std::string message = "udp-message";

    const ssize_t sent = sendto(
        client.get(),
        message.data(),
        message.size(),
        0,
        reinterpret_cast<const sockaddr*>(&serverAddress),
        sizeof(serverAddress)
    );

    if (sent < 0) {
        std::cerr
            << "UDP sendto failed: "
            << std::strerror(errno)
            << "\n";
        return;
    }

    char buffer[4096]{};
    sockaddr_in sender{};
    socklen_t senderLength = sizeof(sender);

    const ssize_t received = recvfrom(
        server.get(),
        buffer,
        sizeof(buffer),
        0,
        reinterpret_cast<sockaddr*>(&sender),
        &senderLength
    );

    if (received < 0) {
        std::cerr
            << "UDP recvfrom failed: "
            << std::strerror(errno)
            << "\n";
        return;
    }

    std::cout
        << "UDP server received: "
        << std::string(buffer, buffer + received)
        << "\n";
}


// ---------------------------------------------------------------------------
// Linux command reference
// ---------------------------------------------------------------------------

void printLinuxCommandReference() {
    section("6. Linux networking command reference");

    std::cout << R"(
Interfaces:
  ip link
      Detailed link information.

  ip -br link
      Compact interface state.

  ip addr
      IP addresses assigned to interfaces.

  ip -br addr
      Compact IP address display.

  ip -s link
      Interface packet and byte statistics.

Routing:
  ip route
      IPv4 routing table.

  ip -6 route
      IPv6 routing table.

  ip route get 8.8.8.8
      Show the route selected for a destination.

Connectivity:
  ping -c 4 example.com
      ICMP reachability test.

Sockets:
  ss -tuln
      Listening TCP and UDP sockets.

  ss -tulpn
      Listening sockets with process information where permitted.

  ss -s
      Socket statistics.

Legacy:
  netstat -tuln
      Legacy socket inspection.

  netstat -rn
      Legacy routing table.

DNS:
  getent hosts example.com
      Query through the system name-service configuration.

  resolvectl status
      Inspect systemd-resolved configuration where available.

  resolvectl query example.com
      Query a name through systemd-resolved.
)";
}


// ---------------------------------------------------------------------------
// Troubleshooting architecture
// ---------------------------------------------------------------------------

void printTroubleshootingWorkflow() {
    section("7. Production troubleshooting workflow");

    std::cout << R"(
Problem: "The application cannot reach a server."

Layer 1: Interface
  ip -br link
  ip -br addr

Questions:
  Is the interface present?
  Is it administratively up?
  Does it have an expected IP address?

Layer 2/3: Route
  ip route
  ip route get <destination>

Questions:
  Is there a route?
  Which interface will be used?
  Is a gateway required?

Layer 3: Connectivity
  ping <destination>

Questions:
  Does IP-level traffic receive a response?
  Is ICMP being filtered?

Name resolution:
  getent hosts <hostname>
  resolvectl query <hostname>

Questions:
  Does the hostname resolve?
  Which IPv4/IPv6 addresses are returned?

Transport:
  ss -tuln
  nc -vz <host> <port>

Questions:
  Is the service listening?
  Is the port reachable?

Application:
  curl -v https://<host>
  application-specific diagnostics

Questions:
  Does the actual protocol work?
  Is authentication, TLS, HTTP, or application logic failing?

The layers must not be conflated. A working route does not imply DNS works.
Successful DNS does not imply a TCP listener exists. A listening TCP socket
does not prove the application protocol is healthy.
)";
}


// ---------------------------------------------------------------------------
// Security considerations
// ---------------------------------------------------------------------------

void printSecurityConsiderations() {
    section("8. Security considerations");

    std::cout << R"(
Binding:
  127.0.0.1
      Limits the service to the local host in ordinary IPv4 configurations.

  0.0.0.0
      Requests listening on all IPv4 interfaces.

Exposure:
  A service that listens on a network-facing interface can become reachable
  by other hosts depending on routing and firewall policy.

Ports:
  Port numbers are identifiers, not security boundaries by themselves.

Input:
  Hostnames, addresses, ports, and application payloads may be untrusted.
  Validate them before use.

Encryption:
  TCP provides reliable transport, not confidentiality. Sensitive data
  normally requires an appropriate encryption protocol such as TLS.

Privileges:
  Some low-numbered ports historically require elevated privileges on Linux.
  Modern deployments can use capabilities, service managers, or reverse
  proxies instead of unnecessarily running an entire application as root.

Diagnostics:
  Socket inspection can expose process and endpoint information. Access to
  detailed process information may be restricted by operating-system policy.
)";
}


// ---------------------------------------------------------------------------
// Edge cases
// ---------------------------------------------------------------------------

void demonstrateEdgeCases() {
    section("9. Edge cases and failure conditions");

    const std::vector<std::string> invalidAddresses = {
        "192.168.1.999",
        "10.10.10",
        "not-an-ip",
        "300.1.1.1"
    };

    for (const auto& address : invalidAddresses) {
        try {
            static_cast<void>(ipv4FromString(address));
            std::cout << address << " unexpectedly accepted.\n";
        } catch (const std::exception& error) {
            std::cout
                << address
                << " rejected: "
                << error.what()
                << "\n";
        }
    }

    for (const int port : {-1, 0, 22, 443, 65535, 65536}) {
        std::cout
            << "port "
            << std::setw(6)
            << port
            << ": "
            << (validPort(port) ? "valid" : "invalid")
            << "\n";
    }

    std::cout << R"(
Important edge cases:
  - A host can have multiple interfaces.
  - A host can have multiple IPv4 and IPv6 addresses.
  - DNS can return multiple addresses.
  - IPv6 may be preferred by an application depending on resolver behavior.
  - ICMP can be blocked.
  - A route can exist while a firewall blocks the application port.
  - A port can be listening only on loopback.
  - A process can terminate between two diagnostic commands.
  - netstat may not be installed.
  - ss output may hide process information without sufficient privileges.
)";
}


// ---------------------------------------------------------------------------
// Assertions
// ---------------------------------------------------------------------------

void runSelfTests() {
    section("10. Self-tests");

    const auto loopback = ipv4FromString("127.0.0.1");

    if (loopback != 0x7f000001u) {
        throw std::runtime_error("IPv4 conversion test failed.");
    }

    IPv4Network privateNetwork{
        ipv4FromString("192.168.1.0"),
        24
    };

    if (!privateNetwork.contains(
        ipv4FromString("192.168.1.25")
    )) {
        throw std::runtime_error("Subnet membership test failed.");
    }

    if (privateNetwork.contains(
        ipv4FromString("192.168.2.25")
    )) {
        throw std::runtime_error("Subnet exclusion test failed.");
    }

    RoutingTable table({
        {
            {ipv4FromString("0.0.0.0"), 0},
            "eth0",
            std::nullopt,
            100
        },
        {
            {ipv4FromString("10.0.0.0"), 8},
            "vpn0",
            std::nullopt,
            100
        },
        {
            {ipv4FromString("10.10.0.0"), 16},
            "vpn1",
            std::nullopt,
            100
        }
    });

    const Route* selected = table.lookup("10.10.20.1");

    if (selected == nullptr ||
        selected->interfaceName != "vpn1") {
        throw std::runtime_error(
            "Longest-prefix routing test failed."
        );
    }

    bool invalidRejected = false;

    try {
        static_cast<void>(ipv4FromString("999.999.999.999"));
    } catch (const std::exception&) {
        invalidRejected = true;
    }

    if (!invalidRejected) {
        throw std::runtime_error(
            "Invalid IPv4 address was accepted."
        );
    }

    if (!validPort(0) ||
        !validPort(65535) ||
        validPort(-1) ||
        validPort(65536)) {
        throw std::runtime_error("Port validation test failed.");
    }

    std::cout << "All self-tests passed.\n";
}

} // namespace netstudy


// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

int main() {
    try {
        std::cout
            << "Linux Networking C++ Technical Case Study\n"
            << "C++ standard: C++17 or later\n";

        netstudy::demonstrateIpAddressing();
        netstudy::demonstrateRouting();
        netstudy::demonstrateDns();
        netstudy::runTcpCaseStudy();
        netstudy::runUdpCaseStudy();
        netstudy::printLinuxCommandReference();
        netstudy::printTroubleshootingWorkflow();
        netstudy::printSecurityConsiderations();
        netstudy::demonstrateEdgeCases();
        netstudy::runSelfTests();

        netstudy::section("11. Case study complete");

        std::cout
            << "The program demonstrated Linux networking concepts without "
            << "modifying the host network configuration.\n";

        return 0;
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << "\n";

        return 1;
    }
}
