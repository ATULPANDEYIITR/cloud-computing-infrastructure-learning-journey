#include <algorithm>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * Network Virtualization Governance and Forwarding Engine
 *
 * C++17 case study:
 * A virtualized data-center fabric hosts multiple tenant networks.
 * Virtual switches provide Layer-2 forwarding, virtual routers provide
 * Layer-3 boundaries, and an overlay fabric carries tenant traffic across
 * physical transport endpoints.
 *
 * The implementation deliberately separates:
 *   - topology and network objects
 *   - data-plane forwarding
 *   - control-plane policy
 *   - overlay encapsulation
 *   - operational failure handling
 */

class IPv4 {
private:
    std::uint32_t value_;

public:
    explicit IPv4(const std::string& text) {
        std::stringstream stream(text);
        unsigned int a, b, c, d;
        char dot1, dot2, dot3;

        if (!(stream >> a >> dot1 >> b >> dot2 >> c >> dot3 >> d) ||
            dot1 != '.' || dot2 != '.' || dot3 != '.' ||
            a > 255 || b > 255 || c > 255 || d > 255) {
            throw std::invalid_argument("Invalid IPv4 address: " + text);
        }

        value_ =
            (a << 24U) |
            (b << 16U) |
            (c << 8U) |
            d;
    }

    std::uint32_t value() const {
        return value_;
    }

    std::string toString() const {
        std::ostringstream out;
        out
            << ((value_ >> 24U) & 0xffU) << '.'
            << ((value_ >> 16U) & 0xffU) << '.'
            << ((value_ >> 8U) & 0xffU) << '.'
            << (value_ & 0xffU);
        return out.str();
    }
};

class CIDR {
private:
    IPv4 network_;
    unsigned prefixLength_;

public:
    CIDR(const std::string& network, unsigned prefixLength)
        : network_(network), prefixLength_(prefixLength) {
        if (prefixLength > 32) {
            throw std::invalid_argument("CIDR prefix must be between 0 and 32");
        }
    }

    bool contains(const IPv4& address) const {
        if (prefixLength_ == 0) {
            return true;
        }

        std::uint32_t mask =
            0xffffffffU << (32U - prefixLength_);

        return (address.value() & mask) ==
               (network_.value() & mask);
    }

    unsigned prefixLength() const {
        return prefixLength_;
    }

    std::string describe() const {
        return network_.toString() + "/" +
               std::to_string(prefixLength_);
    }
};

struct MacAddress {
    std::string value;

    explicit MacAddress(std::string address)
        : value(std::move(address)) {
        if (value.size() != 17) {
            throw std::invalid_argument("Invalid MAC address: " + value);
        }
    }

    bool operator<(const MacAddress& other) const {
        return value < other.value;
    }

    bool operator==(const MacAddress& other) const {
        return value == other.value;
    }
};

struct VirtualNetwork {
    std::string name;
    CIDR subnet;
    unsigned vlanId;
    unsigned vni;
    IPv4 gateway;
    bool isolated;
};

struct VirtualNIC {
    std::string name;
    MacAddress mac;
    IPv4 address;
    std::string network;
    bool enabled{true};
};

struct Host {
    std::string name;
    std::map<std::string, VirtualNIC> interfaces;
};

struct EthernetFrame {
    MacAddress source;
    MacAddress destination;
    IPv4 sourceIp;
    IPv4 destinationIp;
    std::string payload;
    std::optional<unsigned> vlan;
    std::uint8_t ttl{64};
};

class VirtualSwitch {
public:
    struct Port {
        std::string name;
        bool enabled{true};
        std::optional<std::string> nicOwner;
    };

private:
    std::string name_;
    std::map<std::string, Port> ports_;
    std::map<MacAddress, std::string> forwardingTable_;
    std::size_t forwarded_{0};
    std::size_t flooded_{0};
    std::size_t dropped_{0};

public:
    explicit VirtualSwitch(std::string name)
        : name_(std::move(name)) {}

    const std::string& name() const {
        return name_;
    }

    void addPort(
        const std::string& portName,
        std::optional<std::string> nicOwner = std::nullopt
    ) {
        if (ports_.contains(portName)) {
            throw std::invalid_argument("Duplicate virtual switch port");
        }

        ports_.emplace(
            portName,
            Port{portName, true, std::move(nicOwner)}
        );
    }

    void setPortState(const std::string& portName, bool enabled) {
        auto it = ports_.find(portName);

        if (it == ports_.end()) {
            throw std::invalid_argument("Unknown switch port");
        }

        it->second.enabled = enabled;
    }

    std::vector<std::string> receive(
        const EthernetFrame& frame,
        const std::string& ingressPort
    ) {
        auto ingress = ports_.find(ingressPort);

        if (ingress == ports_.end() || !ingress->second.enabled) {
            ++dropped_;
            return {};
        }

        /*
         * MAC learning records the location of the sender. This is a
         * data-plane operation and is independent of the SDN controller.
         */
        forwardingTable_[frame.source] = ingressPort;

        auto destination = forwardingTable_.find(frame.destination);

        if (destination != forwardingTable_.end()) {
            if (destination->second == ingressPort) {
                return {};
            }

            auto destinationPort = ports_.find(destination->second);

            if (destinationPort == ports_.end() ||
                !destinationPort->second.enabled) {
                ++dropped_;
                return {};
            }

            ++forwarded_;
            return {destination->second};
        }

        /*
         * Unknown unicast traffic is flooded. A production switch would
         * also apply VLAN membership, port security, storm-control, and
         * other forwarding constraints.
         */
        std::vector<std::string> outputs;

        for (const auto& [name, port] : ports_) {
            if (name != ingressPort && port.enabled) {
                outputs.push_back(name);
                ++flooded_;
            }
        }

        return outputs;
    }

    void printForwardingTable() const {
        std::cout << "\n[" << name_ << "] forwarding table\n";

        for (const auto& [mac, port] : forwardingTable_) {
            std::cout << "  " << mac.value
                      << " -> " << port << '\n';
        }
    }

    void printStatistics() const {
        std::cout
            << name_
            << " forwarded=" << forwarded_
            << " flooded=" << flooded_
            << " dropped=" << dropped_
            << '\n';
    }
};

enum class PolicyAction {
    Allow,
    Deny
};

class SDNPolicyEngine {
private:
    std::map<std::pair<std::string, std::string>, PolicyAction> policies_;

public:
    void setPolicy(
        const std::string& source,
        const std::string& destination,
        PolicyAction action
    ) {
        policies_[{source, destination}] = action;
    }

    PolicyAction evaluate(
        const std::string& source,
        const std::string& destination
    ) const {
        auto it = policies_.find({source, destination});

        if (it == policies_.end()) {
            /*
             * Default-deny makes an omitted policy explicit rather than
             * silently permitting traffic between logical tenants.
             */
            return PolicyAction::Deny;
        }

        return it->second;
    }
};

class VirtualRouter {
private:
    std::vector<const VirtualNetwork*> networks_;
    const SDNPolicyEngine& policyEngine_;

public:
    VirtualRouter(
        std::vector<const VirtualNetwork*> networks,
        const SDNPolicyEngine& policyEngine
    )
        : networks_(std::move(networks)),
          policyEngine_(policyEngine) {}

    std::optional<std::string> locateNetwork(
        const IPv4& destination
    ) const {
        const VirtualNetwork* bestMatch = nullptr;

        /*
         * Longest-prefix matching matters when virtual networks have
         * overlapping routes. The most specific prefix wins.
         */
        for (const auto* network : networks_) {
            if (network->subnet.contains(destination)) {
                if (
                    bestMatch == nullptr ||
                    network->subnet.prefixLength() >
                    bestMatch->subnet.prefixLength()
                ) {
                    bestMatch = network;
                }
            }
        }

        if (bestMatch == nullptr) {
            return std::nullopt;
        }

        return bestMatch->name;
    }

    bool route(
        EthernetFrame& frame,
        const std::string& sourceNetwork
    ) const {
        if (frame.ttl <= 1) {
            std::cout << "Router dropped packet: TTL expired\n";
            return false;
        }

        auto destinationNetwork = locateNetwork(frame.destinationIp);

        if (!destinationNetwork) {
            std::cout << "Router dropped packet: no destination route\n";
            return false;
        }

        const auto action = policyEngine_.evaluate(
            sourceNetwork,
            *destinationNetwork
        );

        if (action != PolicyAction::Allow) {
            std::cout
                << "Router blocked "
                << sourceNetwork
                << " -> "
                << *destinationNetwork
                << " by policy\n";
            return false;
        }

        --frame.ttl;

        std::cout
            << "Router allowed "
            << sourceNetwork
            << " -> "
            << *destinationNetwork
            << ", TTL="
            << static_cast<unsigned>(frame.ttl)
            << '\n';

        return true;
    }
};

struct OverlayPacket {
    std::string outerSource;
    std::string outerDestination;
    unsigned vni;
    EthernetFrame inner;
};

class OverlayFabric {
private:
    std::string name_;
    std::map<MacAddress, std::string> endpointLocations_;

public:
    explicit OverlayFabric(std::string name)
        : name_(std::move(name)) {}

    void registerEndpoint(
        const MacAddress& mac,
        const std::string& tunnelEndpoint
    ) {
        endpointLocations_[mac] = tunnelEndpoint;
    }

    OverlayPacket encapsulate(
        const EthernetFrame& frame,
        const std::string& outerSource,
        const std::string& outerDestination,
        unsigned vni
    ) const {
        if (vni == 0 || vni > 16'777'215) {
            throw std::invalid_argument("VNI must fit in 24 bits");
        }

        return {
            outerSource,
            outerDestination,
            vni,
            frame
        };
    }

    EthernetFrame decapsulate(
        const OverlayPacket& packet,
        unsigned expectedVni
    ) const {
        if (packet.vni != expectedVni) {
            throw std::runtime_error(
                "Overlay VNI mismatch: packet belongs to another segment"
            );
        }

        return packet.inner;
    }

    void printEndpointDatabase() const {
        std::cout << "\nOverlay endpoint database\n";

        for (const auto& [mac, endpoint] : endpointLocations_) {
            std::cout
                << "  "
                << mac.value
                << " -> VTEP "
                << endpoint
                << '\n';
        }
    }
};

class NetworkFabric {
private:
    std::map<std::string, VirtualNetwork> networks_;
    std::map<std::string, Host> hosts_;
    VirtualSwitch switch_;
    SDNPolicyEngine policyEngine_;
    std::unique_ptr<VirtualRouter> router_;
    OverlayFabric overlay_;

public:
    NetworkFabric()
        : switch_("vswitch-01"),
          overlay_("vxlan-fabric") {}

    void build() {
        networks_.emplace(
            "frontend",
            VirtualNetwork{
                "frontend",
                CIDR("10.10.10.0", 24),
                110,
                5001,
                IPv4("10.10.10.1"),
                false
            }
        );

        networks_.emplace(
            "backend",
            VirtualNetwork{
                "backend",
                CIDR("10.10.20.0", 24),
                120,
                5002,
                IPv4("10.10.20.1"),
                false
            }
        );

        networks_.emplace(
            "database",
            VirtualNetwork{
                "database",
                CIDR("10.10.30.0", 24),
                130,
                5003,
                IPv4("10.10.30.1"),
                true
            }
        );

        policyEngine_.setPolicy(
            "frontend", "frontend", PolicyAction::Allow
        );
        policyEngine_.setPolicy(
            "backend", "backend", PolicyAction::Allow
        );
        policyEngine_.setPolicy(
            "database", "database", PolicyAction::Allow
        );
        policyEngine_.setPolicy(
            "frontend", "backend", PolicyAction::Allow
        );
        policyEngine_.setPolicy(
            "backend", "frontend", PolicyAction::Allow
        );
        policyEngine_.setPolicy(
            "backend", "database", PolicyAction::Allow
        );
        policyEngine_.setPolicy(
            "database", "backend", PolicyAction::Allow
        );
        policyEngine_.setPolicy(
            "frontend", "database", PolicyAction::Deny
        );
        policyEngine_.setPolicy(
            "database", "frontend", PolicyAction::Deny
        );

        std::vector<const VirtualNetwork*> networkPointers;

        for (auto& [name, network] : networks_) {
            networkPointers.push_back(&network);
        }

        router_ = std::make_unique<VirtualRouter>(
            networkPointers,
            policyEngine_
        );

        Host web{"web-01", {}};
        web.interfaces.emplace(
            "eth0",
            VirtualNIC{
                "eth0",
                MacAddress("02:00:00:00:10:01"),
                IPv4("10.10.10.10"),
                "frontend"
            }
        );

        Host app{"app-01", {}};
        app.interfaces.emplace(
            "eth0",
            VirtualNIC{
                "eth0",
                MacAddress("02:00:00:00:20:01"),
                IPv4("10.10.20.10"),
                "backend"
            }
        );

        Host database{"db-01", {}};
        database.interfaces.emplace(
            "eth0",
            VirtualNIC{
                "eth0",
                MacAddress("02:00:00:00:30:01"),
                IPv4("10.10.30.10"),
                "database"
            }
        );

        hosts_.emplace("web-01", std::move(web));
        hosts_.emplace("app-01", std::move(app));
        hosts_.emplace("db-01", std::move(database));

        switch_.addPort(
            "web-port",
            "web-01/eth0"
        );
        switch_.addPort(
            "app-port",
            "app-01/eth0"
        );
        switch_.addPort("overlay-uplink");

        overlay_.registerEndpoint(
            hosts_.at("web-01").interfaces.at("eth0").mac,
            "192.0.2.10"
        );

        overlay_.registerEndpoint(
            hosts_.at("app-01").interfaces.at("eth0").mac,
            "192.0.2.20"
        );

        overlay_.registerEndpoint(
            hosts_.at("db-01").interfaces.at("eth0").mac,
            "192.0.2.30"
        );
    }

    void printTopology() const {
        std::cout << "=== Virtualized data-center fabric ===\n";

        for (const auto& [name, network] : networks_) {
            std::cout
                << "Network "
                << name
                << " subnet="
                << network.subnet.describe()
                << " VLAN="
                << network.vlanId
                << " VNI="
                << network.vni
                << " gateway="
                << network.gateway.toString()
                << " isolated="
                << std::boolalpha
                << network.isolated
                << '\n';
        }

        for (const auto& [name, host] : hosts_) {
            for (const auto& [nicName, nic] : host.interfaces) {
                std::cout
                    << "Host "
                    << name
                    << " NIC="
                    << nicName
                    << " MAC="
                    << nic.mac.value
                    << " IP="
                    << nic.address.toString()
                    << " network="
                    << nic.network
                    << '\n';
            }
        }
    }

    void demonstrateSwitching() {
        std::cout << "\n=== Layer-2 virtual switching ===\n";

        const auto& web = hosts_.at("web-01").interfaces.at("eth0");
        const auto& app = hosts_.at("app-01").interfaces.at("eth0");

        EthernetFrame frame{
            web.mac,
            app.mac,
            web.address,
            app.address,
            "GET /orders",
            110,
            64
        };

        auto first =
            switch_.receive(frame, "web-port");

        std::cout << "First forwarding decision: ";

        for (const auto& port : first) {
            std::cout << port << ' ';
        }

        std::cout << '\n';

        EthernetFrame reply{
            app.mac,
            web.mac,
            app.address,
            web.address,
            "HTTP 200",
            110,
            64
        };

        auto second =
            switch_.receive(reply, "app-port");

        std::cout << "Reply forwarding decision: ";

        for (const auto& port : second) {
            std::cout << port << ' ';
        }

        std::cout << '\n';

        switch_.printForwardingTable();
    }

    void demonstrateRouting() {
        std::cout << "\n=== Inter-network routing ===\n";

        const auto& web = hosts_.at("web-01").interfaces.at("eth0");
        const auto& app = hosts_.at("app-01").interfaces.at("eth0");

        EthernetFrame frame{
            web.mac,
            app.mac,
            web.address,
            app.address,
            "POST /internal/order",
            110,
            64
        };

        router_->route(frame, "frontend");
    }

    void demonstrateOverlay() {
        std::cout << "\n=== Overlay encapsulation ===\n";

        const auto& web = hosts_.at("web-01").interfaces.at("eth0");
        const auto& app = hosts_.at("app-01").interfaces.at("eth0");

        EthernetFrame inner{
            web.mac,
            app.mac,
            web.address,
            app.address,
            "tenant payload",
            std::nullopt,
            64
        };

        OverlayPacket packet =
            overlay_.encapsulate(
                inner,
                "192.0.2.10",
                "192.0.2.20",
                5001
            );

        std::cout
            << "Outer transport: "
            << packet.outerSource
            << " -> "
            << packet.outerDestination
            << '\n';

        std::cout
            << "VNI: "
            << packet.vni
            << '\n';

        auto recovered =
            overlay_.decapsulate(packet, 5001);

        std::cout
            << "Inner destination after decapsulation: "
            << recovered.destinationIp.toString()
            << '\n';

        overlay_.printEndpointDatabase();
    }

    void demonstrateSecurityPolicy() {
        std::cout << "\n=== Logical network policy ===\n";

        const auto& web = hosts_.at("web-01").interfaces.at("eth0");
        const auto& database = hosts_.at("db-01").interfaces.at("eth0");

        EthernetFrame directDatabaseTraffic{
            web.mac,
            database.mac,
            web.address,
            database.address,
            "direct database query",
            110,
            64
        };

        const bool allowed =
            router_->route(
                directDatabaseTraffic,
                "frontend"
            );

        std::cout
            << "Frontend -> database: "
            << (allowed ? "ALLOWED" : "BLOCKED")
            << '\n';
    }

    void demonstrateFailure() {
        std::cout << "\n=== Virtual-port failure ===\n";

        switch_.setPortState("app-port", false);

        const auto& web = hosts_.at("web-01").interfaces.at("eth0");
        const auto& app = hosts_.at("app-01").interfaces.at("eth0");

        EthernetFrame frame{
            web.mac,
            app.mac,
            web.address,
            app.address,
            "traffic during failure",
            110,
            64
        };

        auto result =
            switch_.receive(frame, "web-port");

        std::cout
            << "Forwarding outputs after app-port failure: ";

        if (result.empty()) {
            std::cout << "<none>";
        }

        for (const auto& port : result) {
            std::cout << port << ' ';
        }

        std::cout << '\n';

        switch_.setPortState("app-port", true);
        std::cout << "app-port restored\n";
    }

    void printStatistics() const {
        std::cout << "\n=== Data-plane statistics ===\n";
        switch_.printStatistics();
    }

    void run() {
        printTopology();
        demonstrateSwitching();
        demonstrateRouting();
        demonstrateOverlay();
        demonstrateSecurityPolicy();
        demonstrateFailure();
        printStatistics();
    }
};

int main() {
    try {
        NetworkFabric fabric;
        fabric.build();
        fabric.run();

        std::cout
            << "\nArchitectural model:\n"
            << "Virtual switches perform data-plane forwarding.\n"
            << "Virtual routers provide Layer-3 boundaries.\n"
            << "Overlay networks map logical tenant identity onto an "
               "underlay transport.\n"
            << "An SDN policy engine represents centralized control-plane "
               "intent.\n";
    }
    catch (const std::exception& exception) {
        std::cerr
            << "Network fabric error: "
            << exception.what()
            << '\n';
        return 1;
    }

    return 0;
}
