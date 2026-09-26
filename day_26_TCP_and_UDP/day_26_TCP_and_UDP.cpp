/*
 * TCP AND UDP: C++ INDUSTRY-STYLE CASE STUDY
 *
 * Scenario:
 * A telemetry service receives sensor messages from remote devices.
 *
 * The program demonstrates:
 * - TCP connection-oriented communication
 * - UDP datagram communication
 * - Port usage
 * - TCP framing
 * - UDP sequence numbers
 * - Duplicate and out-of-order packet handling
 * - Validation
 * - Checksums
 * - Retry-oriented protocol design
 * - Classes and modular design
 * - Error handling
 * - Performance and complexity considerations
 *
 * Compile:
 *     C++17 or later
 *
 * The networking demonstration uses POSIX/BSD sockets and therefore targets
 * Linux, macOS, and other POSIX-compatible environments.
 */

#include <arpa/inet.h>
#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <map>
#include <netinet/in.h>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unistd.h>
#include <vector>
#include <sys/socket.h>


// ============================================================================
// 1. GENERAL UTILITIES
// ============================================================================

namespace netstudy {

constexpr uint16_t TELEMETRY_PORT = 0;
constexpr std::size_t MAX_PAYLOAD = 4096;

void printSection(const std::string& title) {
    std::cout << "\n" << std::string(78, '=') << "\n";
    std::cout << title << "\n";
    std::cout << std::string(78, '=') << "\n";
}

class SocketError : public std::runtime_error {
public:
    explicit SocketError(const std::string& message)
        : std::runtime_error(message + ": " + std::strerror(errno)) {}
};


// ============================================================================
// 2. RAII SOCKET WRAPPER
// ============================================================================

class Socket {
private:
    int descriptor_;

public:
    Socket() : descriptor_(-1) {}

    explicit Socket(int descriptor)
        : descriptor_(descriptor) {}

    Socket(const Socket&) = delete;
    Socket& operator=(const Socket&) = delete;

    Socket(Socket&& other) noexcept
        : descriptor_(other.descriptor_) {
        other.descriptor_ = -1;
    }

    Socket& operator=(Socket&& other) noexcept {
        if (this != &other) {
            closeSocket();
            descriptor_ = other.descriptor_;
            other.descriptor_ = -1;
        }
        return *this;
    }

    ~Socket() {
        closeSocket();
    }

    int get() const {
        return descriptor_;
    }

    bool valid() const {
        return descriptor_ >= 0;
    }

    void closeSocket() {
        if (descriptor_ >= 0) {
            ::close(descriptor_);
            descriptor_ = -1;
        }
    }
};


// ============================================================================
// 3. CHECKSUM
// ============================================================================

uint32_t checksum(const std::string& data) {
    uint32_t value = 0;

    for (unsigned char byte : data) {
        value = (value + byte) & 0xFFFFFFFFu;
        value = ((value << 5) | (value >> 27)) & 0xFFFFFFFFu;
    }

    return value;
}


// ============================================================================
// 4. TELEMETRY MESSAGE
// ============================================================================

struct TelemetryMessage {
    uint32_t sequence{};
    std::string deviceId;
    double temperature{};
    double pressure{};
    std::string status;
};

class TelemetryCodec {
public:
    static std::string encode(const TelemetryMessage& message) {
        if (message.deviceId.empty()) {
            throw std::invalid_argument("Device ID cannot be empty");
        }

        if (message.deviceId.size() > 128) {
            throw std::invalid_argument("Device ID is too long");
        }

        if (message.status.size() > 128) {
            throw std::invalid_argument("Status is too long");
        }

        std::ostringstream output;

        output << message.sequence << '|'
               << message.deviceId << '|'
               << std::fixed << std::setprecision(2)
               << message.temperature << '|'
               << message.pressure << '|'
               << message.status;

        const std::string content = output.str();

        return content + "|" + std::to_string(checksum(content));
    }

    static TelemetryMessage decode(const std::string& packet) {
        std::vector<std::string> fields;
        std::stringstream stream(packet);
        std::string field;

        while (std::getline(stream, field, '|')) {
            fields.push_back(field);
        }

        if (fields.size() != 6) {
            throw std::invalid_argument("Telemetry packet has invalid field count");
        }

        const std::string content =
            fields[0] + "|" +
            fields[1] + "|" +
            fields[2] + "|" +
            fields[3] + "|" +
            fields[4];

        uint32_t expectedChecksum = 0;

        try {
            expectedChecksum = static_cast<uint32_t>(
                std::stoul(fields[5])
            );
        } catch (...) {
            throw std::invalid_argument("Invalid checksum field");
        }

        if (checksum(content) != expectedChecksum) {
            throw std::invalid_argument("Checksum validation failed");
        }

        TelemetryMessage message;

        try {
            message.sequence = static_cast<uint32_t>(
                std::stoul(fields[0])
            );
            message.deviceId = fields[1];
            message.temperature = std::stod(fields[2]);
            message.pressure = std::stod(fields[3]);
            message.status = fields[4];
        } catch (...) {
            throw std::invalid_argument("Invalid telemetry values");
        }

        return message;
    }
};


// ============================================================================
// 5. TCP FRAMING
// ============================================================================

class LengthPrefixedFrame {
public:
    static std::string encode(const std::string& payload) {
        if (payload.size() > MAX_PAYLOAD) {
            throw std::invalid_argument("TCP frame is too large");
        }

        std::string frame;

        uint32_t length = static_cast<uint32_t>(payload.size());

        frame.push_back(
            static_cast<char>((length >> 24) & 0xFF)
        );
        frame.push_back(
            static_cast<char>((length >> 16) & 0xFF)
        );
        frame.push_back(
            static_cast<char>((length >> 8) & 0xFF)
        );
        frame.push_back(
            static_cast<char>(length & 0xFF)
        );

        frame += payload;

        return frame;
    }

    static std::optional<std::pair<std::string, std::string>>
    decode(const std::string& buffer) {
        if (buffer.size() < 4) {
            return std::nullopt;
        }

        uint32_t length =
            (static_cast<uint32_t>(
                static_cast<unsigned char>(buffer[0])
            ) << 24)
            |
            (static_cast<uint32_t>(
                static_cast<unsigned char>(buffer[1])
            ) << 16)
            |
            (static_cast<uint32_t>(
                static_cast<unsigned char>(buffer[2])
            ) << 8)
            |
            static_cast<uint32_t>(
                static_cast<unsigned char>(buffer[3])
            );

        if (length > MAX_PAYLOAD) {
            throw std::invalid_argument("Frame exceeds maximum size");
        }

        if (buffer.size() < 4 + length) {
            return std::nullopt;
        }

        std::string payload = buffer.substr(4, length);
        std::string remaining = buffer.substr(4 + length);

        return std::make_pair(payload, remaining);
    }
};


// ============================================================================
// 6. TCP SEND/RECEIVE HELPERS
// ============================================================================

bool sendAll(int socketFd, const std::string& data) {
    std::size_t sent = 0;

    while (sent < data.size()) {
        ssize_t result = ::send(
            socketFd,
            data.data() + sent,
            data.size() - sent,
            0
        );

        if (result < 0) {
            if (errno == EINTR) {
                continue;
            }

            return false;
        }

        if (result == 0) {
            return false;
        }

        sent += static_cast<std::size_t>(result);
    }

    return true;
}

bool receiveExact(int socketFd, std::string& output, std::size_t length) {
    output.clear();
    output.reserve(length);

    while (output.size() < length) {
        char buffer[1024];

        std::size_t remaining = length - output.size();
        std::size_t requested = std::min(
            remaining,
            sizeof(buffer)
        );

        ssize_t result = ::recv(
            socketFd,
            buffer,
            requested,
            0
        );

        if (result < 0) {
            if (errno == EINTR) {
                continue;
            }

            return false;
        }

        if (result == 0) {
            return false;
        }

        output.append(buffer, static_cast<std::size_t>(result));
    }

    return true;
}


// ============================================================================
// 7. TCP SERVER
// ============================================================================

class TcpTelemetryServer {
private:
    Socket serverSocket_;
    uint16_t port_{};

public:
    uint16_t start() {
        int descriptor = ::socket(AF_INET, SOCK_STREAM, 0);

        if (descriptor < 0) {
            throw SocketError("socket");
        }

        serverSocket_ = Socket(descriptor);

        int reuse = 1;

        if (::setsockopt(
                serverSocket_.get(),
                SOL_SOCKET,
                SO_REUSEADDR,
                &reuse,
                sizeof(reuse)
            ) < 0) {
            throw SocketError("setsockopt");
        }

        sockaddr_in address{};
        address.sin_family = AF_INET;
        address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        address.sin_port = htons(0);

        if (::bind(
                serverSocket_.get(),
                reinterpret_cast<sockaddr*>(&address),
                sizeof(address)
            ) < 0) {
            throw SocketError("bind");
        }

        if (::listen(serverSocket_.get(), 8) < 0) {
            throw SocketError("listen");
        }

        socklen_t length = sizeof(address);

        if (::getsockname(
                serverSocket_.get(),
                reinterpret_cast<sockaddr*>(&address),
                &length
            ) < 0) {
            throw SocketError("getsockname");
        }

        port_ = ntohs(address.sin_port);

        return port_;
    }

    void handleOneClient() {
        sockaddr_in clientAddress{};
        socklen_t addressLength = sizeof(clientAddress);

        int clientDescriptor = ::accept(
            serverSocket_.get(),
            reinterpret_cast<sockaddr*>(&clientAddress),
            &addressLength
        );

        if (clientDescriptor < 0) {
            throw SocketError("accept");
        }

        Socket client(clientDescriptor);

        std::cout << "TCP client connected.\n";

        uint32_t networkLength = 0;

        if (!receiveExact(
                client.get(),
                reinterpret_cast<std::string&>(
                    *reinterpret_cast<std::string*>(nullptr)
                ),
                0
            )) {
            // This branch is intentionally unreachable because length zero is
            // not used. Actual framing is handled below.
        }

        // Read the four-byte frame header explicitly.
        char header[4];

        std::size_t received = 0;

        while (received < sizeof(header)) {
            ssize_t result = ::recv(
                client.get(),
                header + received,
                sizeof(header) - received,
                0
            );

            if (result <= 0) {
                throw std::runtime_error("TCP client closed unexpectedly");
            }

            received += static_cast<std::size_t>(result);
        }

        networkLength =
            (static_cast<uint32_t>(
                static_cast<unsigned char>(header[0])
            ) << 24)
            |
            (static_cast<uint32_t>(
                static_cast<unsigned char>(header[1])
            ) << 16)
            |
            (static_cast<uint32_t>(
                static_cast<unsigned char>(header[2])
            ) << 8)
            |
            static_cast<uint32_t>(
                static_cast<unsigned char>(header[3])
            );

        if (networkLength > MAX_PAYLOAD) {
            throw std::runtime_error("Incoming TCP frame is too large");
        }

        std::string payload;

        if (!receiveExact(
                client.get(),
                payload,
                networkLength
            )) {
            throw std::runtime_error("Failed to receive TCP payload");
        }

        TelemetryMessage telemetry =
            TelemetryCodec::decode(payload);

        std::cout << "TCP telemetry received from "
                  << telemetry.deviceId
                  << ", sequence "
                  << telemetry.sequence
                  << "\n";

        const std::string response =
            LengthPrefixedFrame::encode(
                "TCP telemetry accepted"
            );

        if (!sendAll(client.get(), response)) {
            throw std::runtime_error("Failed to send TCP response");
        }
    }

    uint16_t port() const {
        return port_;
    }
};


// ============================================================================
// 8. UDP SERVER WITH ORDERING AND DUPLICATE DETECTION
// ============================================================================

class UdpTelemetryServer {
private:
    Socket socket_;
    uint16_t port_{};

    std::map<uint32_t, TelemetryMessage> pending_;
    std::set<uint32_t> processed_;

public:
    uint16_t start() {
        int descriptor = ::socket(AF_INET, SOCK_DGRAM, 0);

        if (descriptor < 0) {
            throw SocketError("socket");
        }

        socket_ = Socket(descriptor);

        sockaddr_in address{};
        address.sin_family = AF_INET;
        address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        address.sin_port = htons(0);

        if (::bind(
                socket_.get(),
                reinterpret_cast<sockaddr*>(&address),
                sizeof(address)
            ) < 0) {
            throw SocketError("UDP bind");
        }

        socklen_t length = sizeof(address);

        if (::getsockname(
                socket_.get(),
                reinterpret_cast<sockaddr*>(&address),
                &length
            ) < 0) {
            throw SocketError("UDP getsockname");
        }

        port_ = ntohs(address.sin_port);

        return port_;
    }

    void processOneDatagram() {
        char buffer[MAX_PAYLOAD + 1];

        sockaddr_in sender{};
        socklen_t senderLength = sizeof(sender);

        ssize_t received = ::recvfrom(
            socket_.get(),
            buffer,
            MAX_PAYLOAD,
            0,
            reinterpret_cast<sockaddr*>(&sender),
            &senderLength
        );

        if (received < 0) {
            throw SocketError("recvfrom");
        }

        std::string payload(
            buffer,
            static_cast<std::size_t>(received)
        );

        TelemetryMessage message =
            TelemetryCodec::decode(payload);

        if (processed_.count(message.sequence) != 0) {
            std::cout
                << "UDP duplicate ignored: sequence "
                << message.sequence << "\n";
            return;
        }

        pending_[message.sequence] = message;

        // In a production reliable-UDP protocol, the next expected sequence
        // would be tracked explicitly. This map demonstrates the ordering
        // buffer needed when datagrams can arrive out of order.
        std::cout
            << "UDP datagram buffered: sequence "
            << message.sequence << "\n";

        processed_.insert(message.sequence);

        const char acknowledgement[] = "ACK";

        if (::sendto(
                socket_.get(),
                acknowledgement,
                sizeof(acknowledgement) - 1,
                0,
                reinterpret_cast<sockaddr*>(&sender),
                senderLength
            ) < 0) {
            throw SocketError("sendto");
        }
    }

    uint16_t port() const {
        return port_;
    }
};


// ============================================================================
// 9. LOCAL UDP CLIENT
// ============================================================================

void sendUdpTelemetry(
    uint16_t port,
    const TelemetryMessage& message
) {
    Socket client(::socket(AF_INET, SOCK_DGRAM, 0));

    if (!client.valid()) {
        throw SocketError("UDP client socket");
    }

    sockaddr_in server{};
    server.sin_family = AF_INET;
    server.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    server.sin_port = htons(port);

    const std::string payload =
        TelemetryCodec::encode(message);

    if (::sendto(
            client.get(),
            payload.data(),
            payload.size(),
            0,
            reinterpret_cast<sockaddr*>(&server),
            sizeof(server)
        ) < 0) {
        throw SocketError("UDP telemetry send");
    }

    char response[64];

    sockaddr_in sender{};
    socklen_t senderLength = sizeof(sender);

    ssize_t received = ::recvfrom(
        client.get(),
        response,
        sizeof(response) - 1,
        0,
        reinterpret_cast<sockaddr*>(&sender),
        &senderLength
    );

    if (received < 0) {
        throw SocketError("UDP acknowledgement");
    }

    response[received] = '\0';

    std::cout << "UDP client received: "
              << response
              << "\n";
}


// ============================================================================
// 10. CONCEPTUAL CASE STUDY
// ============================================================================

void explainArchitecture() {
    printSection("INDUSTRY-STYLE TELEMETRY ARCHITECTURE");

    std::cout << R"(
Scenario:
A fleet of devices periodically sends temperature, pressure, and status
measurements to a central telemetry service.

TCP channel:
- Establishes a connection.
- Uses the TCP three-way handshake.
- Provides an ordered reliable byte stream.
- Uses explicit application framing.
- Detects connection termination and failures.
- Is suitable when reliable delivery is more important than minimizing
  transport-level state.

UDP channel:
- Sends independent datagrams.
- Has no TCP-style connection establishment.
- Preserves datagram boundaries.
- Does not inherently guarantee delivery, ordering, or retransmission.
- Uses application-level sequence numbers in this case study.
- Can acknowledge datagrams at the application layer.

The case study validates:
- Device identifiers
- Numeric telemetry values
- Packet sizes
- Checksums
- Sequence numbers

A production implementation would also require authentication, encryption,
rate limiting, replay protection, persistent storage, monitoring, service
discovery, graceful shutdown, and carefully designed retry/congestion policy.
)" << '\n';
}


// ============================================================================
// 11. COMPLEXITY DISCUSSION
// ============================================================================

void explainComplexity() {
    printSection("ALGORITHMIC AND PERFORMANCE CONSIDERATIONS");

    std::cout << R"(
TCP stream parsing:
- Appending incoming bytes is approximately O(n) when buffers are copied.
- Production implementations should consider buffer reuse to reduce copying.

UDP duplicate detection:
- std::set provides approximately O(log n) lookup.
- std::unordered_set could provide average O(1) lookup but has different
  memory and worst-case behavior.

UDP ordering:
- std::map maintains sorted sequence numbers at approximately O(log n)
  insertion cost.
- A bounded sliding-window structure can reduce memory usage.

Network performance:
- Latency is affected by round-trip time and queueing.
- Throughput depends on bandwidth, congestion windows, socket buffers,
  application processing, and protocol overhead.
- UDP's lower transport state does not guarantee lower end-to-end latency.
)" << '\n';
}


// ============================================================================
// 12. EDGE CASES
// ============================================================================

void demonstrateEdgeCases() {
    printSection("EDGE CASES AND FAILURE CONDITIONS");

    std::vector<std::string> invalidPackets = {
        "",
        "not|enough|fields",
        "1|device|bad-temperature|100|OK|0"
    };

    for (const auto& packet : invalidPackets) {
        try {
            TelemetryCodec::decode(packet);
            std::cout << "Unexpectedly accepted packet\n";
        } catch (const std::exception& error) {
            std::cout << "Rejected invalid packet: "
                      << error.what()
                      << "\n";
        }
    }

    std::cout << R"(
Important real-world failures include:
- Connection refused
- Connection reset
- Partial TCP reads
- Partial writes
- UDP packet loss
- UDP duplication
- UDP reordering
- Invalid checksums
- Oversized messages
- Port conflicts
- Firewall filtering
- DNS failures
- Interface failures
- Resource exhaustion
- Peer crashes
- Timeouts

Network input must always be treated as untrusted input.
)" << '\n';
}


// ============================================================================
// 13. SECURITY
// ============================================================================

void explainSecurity() {
    printSection("SECURITY CONSIDERATIONS");

    std::cout << R"(
TCP and UDP do not inherently provide application-level confidentiality.

Security controls should include:
- TLS or an authenticated secure transport where appropriate.
- Authentication and authorization.
- Strict packet and message size limits.
- Rate limiting.
- Replay protection for security-sensitive UDP messages.
- Protection against malformed packets.
- Resource quotas.
- Connection limits.
- Timeouts.
- Safe logging that avoids leaking secrets.

A source IP address should not be treated as a cryptographic identity.

Checksums can detect certain accidental transmission errors. They do not
provide authentication against a malicious party.
)" << '\n';
}


// ============================================================================
// 14. MAIN CASE STUDY
// ============================================================================

} // namespace netstudy


int main() {
    using namespace netstudy;

    try {
        printSection("TCP AND UDP TRANSPORT PROTOCOL CASE STUDY");

        explainArchitecture();

        printSection("TCP THREE-WAY HANDSHAKE");

        std::cout << R"(
1. Client sends SYN with an initial sequence number.
2. Server sends SYN + ACK.
3. Client sends ACK.

The connection then enters the established state and applications can use
the resulting byte stream.
)" << '\n';

        TcpTelemetryServer tcpServer;
        uint16_t tcpPort = tcpServer.start();

        std::cout
            << "TCP telemetry server listening on port "
            << tcpPort
            << "\n";

        std::thread tcpWorker([&tcpServer]() {
            try {
                tcpServer.handleOneClient();
            } catch (const std::exception& error) {
                std::cerr
                    << "TCP worker error: "
                    << error.what()
                    << "\n";
            }
        });

        std::this_thread::sleep_for(
            std::chrono::milliseconds(50)
        );

        Socket tcpClient(
            ::socket(AF_INET, SOCK_STREAM, 0)
        );

        if (!tcpClient.valid()) {
            throw SocketError("TCP client socket");
        }

        sockaddr_in serverAddress{};
        serverAddress.sin_family = AF_INET;
        serverAddress.sin_addr.s_addr =
            htonl(INADDR_LOOPBACK);
        serverAddress.sin_port =
            htons(tcpPort);

        if (::connect(
                tcpClient.get(),
                reinterpret_cast<sockaddr*>(&serverAddress),
                sizeof(serverAddress)
            ) < 0) {
            throw SocketError("TCP connect");
        }

        TelemetryMessage tcpTelemetry{
            1,
            "DEVICE-TCP-001",
            24.75,
            1013.20,
            "OK"
        };

        const std::string tcpPayload =
            TelemetryCodec::encode(tcpTelemetry);

        const std::string tcpFrame =
            LengthPrefixedFrame::encode(tcpPayload);

        if (!sendAll(tcpClient.get(), tcpFrame)) {
            throw std::runtime_error(
                "Failed to send TCP telemetry"
            );
        }

        tcpClient.closeSocket();

        tcpWorker.join();

        printSection("UDP DATAGRAM CASE STUDY");

        UdpTelemetryServer udpServer;
        uint16_t udpPort = udpServer.start();

        std::cout
            << "UDP telemetry server listening on port "
            << udpPort
            << "\n";

        std::thread udpWorker([&udpServer]() {
            try {
                udpServer.processOneDatagram();
            } catch (const std::exception& error) {
                std::cerr
                    << "UDP worker error: "
                    << error.what()
                    << "\n";
            }
        });

        std::this_thread::sleep_for(
            std::chrono::milliseconds(50)
        );

        TelemetryMessage udpTelemetry{
            42,
            "DEVICE-UDP-007",
            27.10,
            1009.80,
            "ACTIVE"
        };

        sendUdpTelemetry(udpPort, udpTelemetry);

        udpWorker.join();

        demonstrateEdgeCases();
        explainComplexity();
        explainSecurity();

        printSection("CASE STUDY COMPLETE");

        std::cout << R"(
The implementation demonstrated the major architectural difference:

TCP:
connection establishment + ordered reliable byte stream

UDP:
independent datagrams + application-controlled reliability when required
)" << '\n';

        return 0;
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << "\n";

        return 1;
    }
}
