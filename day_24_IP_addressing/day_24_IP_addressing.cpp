/*
 * IP Addressing Industry-Style Case Study
 *
 * Topic:
 *   IPv4, IPv6, public IP, private IP, reserved addresses, subnetting,
 *   VLSM, IP allocation, DHCP-style allocation, NAT, and routing.
 *
 * Standard:
 *   C++17
 *
 * The program models an enterprise network address-management and routing
 * environment using only the C++ standard library.
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
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

using namespace std;

// =============================================================================
// 1. IPv4 ADDRESS CLASS
// =============================================================================

class IPv4 {
private:
    uint32_t value_{};

public:
    IPv4() = default;

    explicit IPv4(uint32_t value) : value_(value) {}

    static IPv4 parse(const string& text) {
        array<unsigned int, 4> octets{};
        char separator1{}, separator2{}, separator3{};

        stringstream stream(text);

        if (!(stream >> octets[0] >> separator1
                     >> octets[1] >> separator2
                     >> octets[2] >> separator3
                     >> octets[3])) {
            throw invalid_argument("Invalid IPv4 address: " + text);
        }

        if (separator1 != '.' || separator2 != '.' || separator3 != '.') {
            throw invalid_argument("Invalid IPv4 separators: " + text);
        }

        for (unsigned int octet : octets) {
            if (octet > 255) {
                throw invalid_argument("IPv4 octet exceeds 255: " + text);
            }
        }

        return IPv4(
            (octets[0] << 24) |
            (octets[1] << 16) |
            (octets[2] << 8) |
            octets[3]
        );
    }

    uint32_t value() const {
        return value_;
    }

    string toString() const {
        return to_string((value_ >> 24) & 0xff) + "." +
               to_string((value_ >> 16) & 0xff) + "." +
               to_string((value_ >> 8) & 0xff) + "." +
               to_string(value_ & 0xff);
    }

    bool operator<(const IPv4& other) const {
        return value_ < other.value_;
    }

    bool operator==(const IPv4& other) const {
        return value_ == other.value_;
    }

    bool operator!=(const IPv4& other) const {
        return !(*this == other);
    }
};

// =============================================================================
// 2. IPv4 CIDR NETWORK
// =============================================================================

class IPv4Network {
private:
    IPv4 networkAddress_;
    unsigned int prefixLength_{};

public:
    IPv4Network(IPv4 address, unsigned int prefixLength)
        : prefixLength_(prefixLength) {

        if (prefixLength > 32) {
            throw invalid_argument("IPv4 prefix must be between 0 and 32.");
        }

        uint32_t mask =
            prefixLength == 0
                ? 0u
                : 0xffffffffu << (32 - prefixLength);

        networkAddress_ = IPv4(address.value() & mask);
    }

    static IPv4Network parse(const string& cidr) {
        const size_t slash = cidr.find('/');

        if (slash == string::npos) {
            throw invalid_argument("CIDR must contain '/': " + cidr);
        }

        const string addressText = cidr.substr(0, slash);
        const string prefixText = cidr.substr(slash + 1);

        unsigned long prefix = stoul(prefixText);

        return IPv4Network(
            IPv4::parse(addressText),
            static_cast<unsigned int>(prefix)
        );
    }

    IPv4 network() const {
        return networkAddress_;
    }

    unsigned int prefix() const {
        return prefixLength_;
    }

    uint64_t addressCount() const {
        return uint64_t{1} << (32 - prefixLength_);
    }

    IPv4 broadcast() const {
        const uint64_t count = addressCount();
        const uint64_t end =
            static_cast<uint64_t>(networkAddress_.value()) +
            count - 1;

        return IPv4(static_cast<uint32_t>(end));
    }

    bool contains(IPv4 address) const {
        const uint32_t mask =
            prefixLength_ == 0
                ? 0u
                : 0xffffffffu << (32 - prefixLength_);

        return (address.value() & mask) ==
               (networkAddress_.value() & mask);
    }

    bool overlaps(const IPv4Network& other) const {
        return contains(other.network()) ||
               contains(other.broadcast()) ||
               other.contains(network()) ||
               other.contains(broadcast());
    }

    string toString() const {
        return network().toString() + "/" + to_string(prefix());
    }
};

// =============================================================================
// 3. ADDRESS CLASSIFICATION
// =============================================================================

enum class AddressCategory {
    PublicCandidate,
    Private,
    Loopback,
    LinkLocal,
    SharedAddressSpace,
    Documentation,
    Multicast,
    Unspecified,
    LimitedBroadcast
};

string categoryName(AddressCategory category) {
    switch (category) {
        case AddressCategory::PublicCandidate:
            return "Public/global candidate";
        case AddressCategory::Private:
            return "RFC 1918 private";
        case AddressCategory::Loopback:
            return "Loopback";
        case AddressCategory::LinkLocal:
            return "Link-local";
        case AddressCategory::SharedAddressSpace:
            return "Shared address space";
        case AddressCategory::Documentation:
            return "Documentation";
        case AddressCategory::Multicast:
            return "Multicast";
        case AddressCategory::Unspecified:
            return "Unspecified";
        case AddressCategory::LimitedBroadcast:
            return "Limited broadcast";
    }

    return "Unknown";
}

AddressCategory classifyIPv4(IPv4 address) {
    static const vector<pair<IPv4Network, AddressCategory>> ranges = {
        {IPv4Network::parse("10.0.0.0/8"), AddressCategory::Private},
        {IPv4Network::parse("172.16.0.0/12"), AddressCategory::Private},
        {IPv4Network::parse("192.168.0.0/16"), AddressCategory::Private},
        {IPv4Network::parse("100.64.0.0/10"), AddressCategory::SharedAddressSpace},
        {IPv4Network::parse("127.0.0.0/8"), AddressCategory::Loopback},
        {IPv4Network::parse("169.254.0.0/16"), AddressCategory::LinkLocal},
        {IPv4Network::parse("192.0.2.0/24"), AddressCategory::Documentation},
        {IPv4Network::parse("198.51.100.0/24"), AddressCategory::Documentation},
        {IPv4Network::parse("203.0.113.0/24"), AddressCategory::Documentation},
        {IPv4Network::parse("224.0.0.0/4"), AddressCategory::Multicast}
    };

    if (address.value() == 0) {
        return AddressCategory::Unspecified;
    }

    if (address.value() == 0xffffffffu) {
        return AddressCategory::LimitedBroadcast;
    }

    for (const auto& [network, category] : ranges) {
        if (network.contains(address)) {
            return category;
        }
    }

    return AddressCategory::PublicCandidate;
}

// =============================================================================
// 4. IPAM ALLOCATION MODEL
// =============================================================================

struct Allocation {
    string owner;
    string purpose;
    IPv4Network network;
};

class IPAM {
private:
    IPv4Network pool_;
    vector<Allocation> allocations_;

public:
    explicit IPAM(const IPv4Network& pool)
        : pool_(pool) {}

    const vector<Allocation>& allocations() const {
        return allocations_;
    }

    IPv4Network allocate(
        const string& owner,
        unsigned int prefix,
        const string& purpose
    ) {
        if (prefix < pool_.prefix()) {
            throw invalid_argument(
                "Requested subnet is larger than the IPAM pool."
            );
        }

        if (prefix > 32) {
            throw invalid_argument("IPv4 prefix cannot exceed 32.");
        }

        const uint64_t blockSize = uint64_t{1} << (32 - prefix);

        const uint64_t poolStart = pool_.network().value();
        const uint64_t poolEnd = pool_.broadcast().value();

        // Search aligned subnet boundaries. Real IPAM systems generally use
        // indexed allocation structures rather than a simple linear scan.
        for (
            uint64_t start = poolStart;
            start + blockSize - 1 <= poolEnd;
            start += blockSize
        ) {
            IPv4Network candidate(
                IPv4(static_cast<uint32_t>(start)),
                prefix
            );

            bool conflict = false;

            for (const Allocation& allocation : allocations_) {
                if (candidate.overlaps(allocation.network)) {
                    conflict = true;
                    break;
                }
            }

            if (!conflict) {
                allocations_.push_back({
                    owner,
                    purpose,
                    candidate
                });

                return candidate;
            }
        }

        throw runtime_error("No suitable subnet remains in the IPAM pool.");
    }

    void release(const string& networkText) {
        IPv4Network target = IPv4Network::parse(networkText);

        const auto oldSize = allocations_.size();

        allocations_.erase(
            remove_if(
                allocations_.begin(),
                allocations_.end(),
                [&](const Allocation& allocation) {
                    return allocation.network.toString() ==
                           target.toString();
                }
            ),
            allocations_.end()
        );

        if (allocations_.size() == oldSize) {
            throw runtime_error(
                "Requested allocation does not exist: " +
                networkText
            );
        }
    }

    void print() const {
        cout << left
             << setw(16) << "Owner"
             << setw(22) << "Network"
             << "Purpose\n";

        cout << string(70, '-') << '\n';

        for (const Allocation& allocation : allocations_) {
            cout << left
                 << setw(16) << allocation.owner
                 << setw(22) << allocation.network.toString()
                 << allocation.purpose << '\n';
        }
    }
};

// =============================================================================
// 5. VLSM PLANNING
// =============================================================================

struct HostRequirement {
    string name;
    uint64_t hosts;
};

unsigned int minimumPrefixForHosts(uint64_t requiredHosts) {
    if (requiredHosts == 0) {
        throw invalid_argument("Host requirement must be positive.");
    }

    for (unsigned int hostBits = 0; hostBits <= 32; ++hostBits) {
        const uint64_t addresses = uint64_t{1} << hostBits;

        // Traditional IPv4 subnet planning reserves network and broadcast
        // addresses for prefixes up to /30.
        if (addresses >= requiredHosts + 2) {
            return 32 - hostBits;
        }
    }

    throw invalid_argument("Host requirement cannot fit into IPv4.");
}

vector<pair<string, IPv4Network>> allocateVLSM(
    const IPv4Network& base,
    vector<HostRequirement> requirements
) {
    sort(
        requirements.begin(),
        requirements.end(),
        [](const HostRequirement& a, const HostRequirement& b) {
            return a.hosts > b.hosts;
        }
    );

    vector<pair<string, IPv4Network>> result;

    uint64_t cursor = base.network().value();
    const uint64_t end = base.broadcast().value();

    for (const auto& requirement : requirements) {
        const unsigned int prefix =
            minimumPrefixForHosts(requirement.hosts);

        const uint64_t blockSize =
            uint64_t{1} << (32 - prefix);

        // Align the next allocation to the subnet boundary.
        const uint64_t aligned =
            ((cursor + blockSize - 1) / blockSize) * blockSize;

        if (aligned + blockSize - 1 > end) {
            throw runtime_error(
                "VLSM requirements do not fit into the base network."
            );
        }

        IPv4Network network(
            IPv4(static_cast<uint32_t>(aligned)),
            prefix
        );

        result.push_back({requirement.name, network});

        cursor = aligned + blockSize;
    }

    return result;
}

// =============================================================================
// 6. DHCP-STYLE LEASE MANAGER
// =============================================================================

class DHCPLeaseManager {
private:
    IPv4Network network_;
    set<uint32_t> excluded_;
    map<string, IPv4> leases_;

public:
    DHCPLeaseManager(
        const IPv4Network& network,
        vector<IPv4> excluded
    )
        : network_(network) {

        for (const IPv4& address : excluded) {
            if (!network_.contains(address)) {
                throw invalid_argument(
                    "Excluded address is outside DHCP network."
                );
            }

            excluded_.insert(address.value());
        }
    }

    IPv4 offer(const string& clientId) {
        auto existing = leases_.find(clientId);

        if (existing != leases_.end()) {
            return existing->second;
        }

        const uint64_t start = network_.network().value();
        const uint64_t end = network_.broadcast().value();

        // Skip network and broadcast addresses in this traditional IPv4
        // DHCP model.
        for (uint64_t value = start + 1; value < end; ++value) {
            if (excluded_.contains(static_cast<uint32_t>(value))) {
                continue;
            }

            bool alreadyLeased = false;

            for (const auto& [client, address] : leases_) {
                if (address.value() == value) {
                    alreadyLeased = true;
                    break;
                }
            }

            if (!alreadyLeased) {
                IPv4 address(static_cast<uint32_t>(value));
                leases_[clientId] = address;
                return address;
            }
        }

        throw runtime_error("DHCP address pool is exhausted.");
    }

    void release(const string& clientId) {
        leases_.erase(clientId);
    }
};

// =============================================================================
// 7. NAT/PAT TRANSLATION
// =============================================================================

struct NatEntry {
    IPv4 privateAddress;
    uint16_t privatePort;
    IPv4 publicAddress;
    uint16_t publicPort;
    IPv4 destinationAddress;
    uint16_t destinationPort;
};

class NatTable {
private:
    IPv4 publicAddress_;
    uint16_t nextPort_;
    vector<NatEntry> entries_;

public:
    explicit NatTable(
        IPv4 publicAddress,
        uint16_t startingPort = 40000
    )
        : publicAddress_(publicAddress),
          nextPort_(startingPort) {}

    NatEntry translate(
        IPv4 privateAddress,
        uint16_t privatePort,
        IPv4 destinationAddress,
        uint16_t destinationPort
    ) {
        if (classifyIPv4(privateAddress) != AddressCategory::Private) {
            throw invalid_argument(
                "Educational NAT model requires an RFC 1918 source."
            );
        }

        if (nextPort_ == numeric_limits<uint16_t>::max()) {
            throw runtime_error("NAT port allocation exhausted.");
        }

        NatEntry entry{
            privateAddress,
            privatePort,
            publicAddress_,
            nextPort_++,
            destinationAddress,
            destinationPort
        };

        entries_.push_back(entry);

        return entry;
    }

    void print() const {
        for (const NatEntry& entry : entries_) {
            cout
                << entry.privateAddress.toString()
                << ":" << entry.privatePort
                << " -> "
                << entry.publicAddress.toString()
                << ":" << entry.publicPort
                << " -> "
                << entry.destinationAddress.toString()
                << ":" << entry.destinationPort
                << '\n';
        }
    }
};

// =============================================================================
// 8. ROUTING TABLE
// =============================================================================

struct Route {
    IPv4Network network;
    string nextHop;
};

class RoutingTable {
private:
    vector<Route> routes_;

public:
    void addRoute(
        const string& networkText,
        const string& nextHop
    ) {
        routes_.push_back({
            IPv4Network::parse(networkText),
            nextHop
        });
    }

    optional<Route> lookup(IPv4 destination) const {
        const Route* best = nullptr;

        for (const Route& route : routes_) {
            if (!route.network.contains(destination)) {
                continue;
            }

            if (
                best == nullptr ||
                route.network.prefix() > best->network.prefix()
            ) {
                best = &route;
            }
        }

        if (best == nullptr) {
            return nullopt;
        }

        return *best;
    }
};

// =============================================================================
// 9. ENTERPRISE NETWORK MODEL
// =============================================================================

struct Site {
    string name;
    IPv4Network network;
};

class EnterpriseNetwork {
private:
    vector<Site> sites_;
    IPAM ipam_;
    RoutingTable routing_;

public:
    explicit EnterpriseNetwork(const IPv4Network& ipamPool)
        : ipam_(ipamPool) {}

    void createSite(
        const string& name,
        unsigned int prefix
    ) {
        IPv4Network network =
            ipam_.allocate(name, prefix, "site address space");

        sites_.push_back({name, network});
    }

    IPAM& ipam() {
        return ipam_;
    }

    RoutingTable& routing() {
        return routing_;
    }

    void printSites() const {
        cout << "\nEnterprise sites:\n";

        for (const Site& site : sites_) {
            cout
                << "  "
                << left
                << setw(16)
                << site.name
                << site.network.toString()
                << '\n';
        }
    }
};

// =============================================================================
// 10. DIAGNOSTIC OUTPUT
// =============================================================================

void printAddressClassification(const string& addressText) {
    IPv4 address = IPv4::parse(addressText);
    AddressCategory category = classifyIPv4(address);

    cout
        << left
        << setw(18)
        << addressText
        << categoryName(category)
        << '\n';
}

void demonstrateIPv4Fundamentals() {
    cout << "\n"
         << string(80, '=')
         << "\nIPv4 fundamentals\n"
         << string(80, '=')
         << '\n';

    const IPv4 address = IPv4::parse("192.168.10.25");

    cout << "Address: " << address.toString() << '\n';
    cout << "Integer: " << address.value() << '\n';

    cout << "Binary:  ";

    for (int bit = 31; bit >= 0; --bit) {
        cout << ((address.value() >> bit) & 1u);

        if (bit % 8 == 0 && bit != 0) {
            cout << ' ';
        }
    }

    cout << '\n';
}

void demonstrateClassification() {
    cout << "\n"
         << string(80, '=')
         << "\nAddress classification\n"
         << string(80, '=')
         << '\n';

    const vector<string> addresses = {
        "0.0.0.0",
        "8.8.8.8",
        "10.1.2.3",
        "100.64.1.1",
        "127.0.0.1",
        "169.254.1.1",
        "172.16.10.10",
        "192.168.1.20",
        "192.0.2.10",
        "203.0.113.20",
        "224.0.0.1",
        "255.255.255.255"
    };

    for (const string& address : addresses) {
        printAddressClassification(address);
    }
}

void demonstrateSubnetting() {
    cout << "\n"
         << string(80, '=')
         << "\nCIDR and subnetting\n"
         << string(80, '=')
         << '\n';

    const vector<string> networks = {
        "192.168.1.0/24",
        "10.20.0.0/16",
        "172.16.32.0/20",
        "192.0.2.8/30",
        "192.0.2.10/31",
        "192.0.2.10/32"
    };

    for (const string& text : networks) {
        IPv4Network network = IPv4Network::parse(text);

        cout
            << left
            << setw(20)
            << text
            << "network=" << setw(18)
            << network.network().toString()
            << "broadcast=" << setw(18)
            << network.broadcast().toString()
            << "addresses=" << network.addressCount()
            << '\n';
    }
}

void demonstrateVLSM() {
    cout << "\n"
         << string(80, '=')
         << "\nVLSM planning\n"
         << string(80, '=')
         << '\n';

    const IPv4Network base =
        IPv4Network::parse("192.168.50.0/24");

    vector<HostRequirement> requirements = {
        {"Engineering", 100},
        {"Operations", 50},
        {"Finance", 30},
        {"Management", 10},
        {"Point-to-point", 2}
    };

    const auto allocations =
        allocateVLSM(base, requirements);

    for (const auto& [name, network] : allocations) {
        cout
            << left
            << setw(16)
            << name
            << network.toString()
            << " addresses=" << network.addressCount()
            << '\n';
    }
}

void demonstrateIPAM() {
    cout << "\n"
         << string(80, '=')
         << "\nEnterprise IPAM\n"
         << string(80, '=')
         << '\n';

    EnterpriseNetwork enterprise(
        IPv4Network::parse("10.50.0.0/16")
    );

    enterprise.createSite("Engineering", 24);
    enterprise.createSite("Finance", 26);
    enterprise.createSite("Operations", 25);
    enterprise.createSite("Security", 27);

    enterprise.printSites();

    cout << "\nIPAM allocation table:\n";
    enterprise.ipam().print();

    cout << "\nReleasing Finance allocation...\n";

    try {
        enterprise.ipam().release("10.50.1.0/26");
    }
    catch (const exception& error) {
        cout << "Release error: " << error.what() << '\n';
    }

    enterprise.ipam().print();
}

void demonstrateDHCP() {
    cout << "\n"
         << string(80, '=')
         << "\nDHCP-style allocation\n"
         << string(80, '=')
         << '\n';

    DHCPLeaseManager dhcp(
        IPv4Network::parse("192.168.60.0/24"),
        {
            IPv4::parse("192.168.60.1"),
            IPv4::parse("192.168.60.2"),
            IPv4::parse("192.168.60.10")
        }
    );

    for (const string& client : {
        "laptop-A",
        "laptop-B",
        "printer-A",
        "phone-A"
    }) {
        cout
            << left
            << setw(14)
            << client
            << " -> "
            << dhcp.offer(client).toString()
            << '\n';
    }

    cout
        << "laptop-A again -> "
        << dhcp.offer("laptop-A").toString()
        << '\n';

    dhcp.release("phone-A");

    cout
        << "tablet-A after release -> "
        << dhcp.offer("tablet-A").toString()
        << '\n';
}

void demonstrateNAT() {
    cout << "\n"
         << string(80, '=')
         << "\nNAT/PAT translation\n"
         << string(80, '=')
         << '\n';

    NatTable nat(IPv4::parse("203.0.113.10"));

    nat.translate(
        IPv4::parse("192.168.1.10"),
        51500,
        IPv4::parse("93.184.216.34"),
        443
    );

    nat.translate(
        IPv4::parse("192.168.1.11"),
        51501,
        IPv4::parse("142.250.72.14"),
        443
    );

    nat.translate(
        IPv4::parse("10.0.0.25"),
        51502,
        IPv4::parse("198.51.100.50"),
        80
    );

    nat.print();
}

void demonstrateRouting() {
    cout << "\n"
         << string(80, '=')
         << "\nRouting and longest-prefix match\n"
         << string(80, '=')
         << '\n';

    RoutingTable routing;

    routing.addRoute("0.0.0.0/0", "Internet Gateway");
    routing.addRoute("10.0.0.0/8", "Router A");
    routing.addRoute("10.20.0.0/16", "Router B");
    routing.addRoute("10.20.30.0/24", "Router C");
    routing.addRoute("10.20.30.128/25", "Router D");

    const vector<string> destinations = {
        "8.8.8.8",
        "10.5.5.5",
        "10.20.5.5",
        "10.20.30.50",
        "10.20.30.200"
    };

    for (const string& destinationText : destinations) {
        IPv4 destination =
            IPv4::parse(destinationText);

        const auto route =
            routing.lookup(destination);

        if (route.has_value()) {
            cout
                << left
                << setw(18)
                << destinationText
                << " -> "
                << setw(20)
                << route->network.toString()
                << route->nextHop
                << '\n';
        }
        else {
            cout
                << destinationText
                << " -> no route\n";
        }
    }
}

void demonstrateNetworkSecurity() {
    cout << "\n"
         << string(80, '=')
         << "\nSecurity design considerations\n"
         << string(80, '=')
         << '\n';

    cout << R"(
1. Private IP space is not a trust boundary.
2. Public IP space is not synonymous with insecure systems.
3. NAT is not a replacement for a firewall.
4. Security rules should cover both IPv4 and IPv6.
5. NAT logging can be necessary to correlate public flows with internal hosts.
6. IP addresses are not complete identities.
7. Documentation prefixes should not be used as production public addresses.
8. Network segmentation requires routing and access-control policy.
)";
}

void demonstrateEdgeCases() {
    cout << "\n"
         << string(80, '=')
         << "\nEdge cases\n"
         << string(80, '=')
         << '\n';

    cout << "/0 address count: "
         << IPv4Network::parse("0.0.0.0/0").addressCount()
         << '\n';

    cout << "/32 address count: "
         << IPv4Network::parse("192.0.2.10/32").addressCount()
         << '\n';

    cout << R"(
IPv4 /31:
  Commonly used for point-to-point links under RFC 3021.
  Traditional network/broadcast host calculations do not apply in the
  same way as a conventional LAN subnet.

IPv4 /32:
  Represents one address and is commonly used for host routes.

IPv6:
  Uses 128-bit addresses.
  IPv6 does not use broadcast.
  Multicast replaces many broadcast functions.
  A /64 is common for an IPv6 subnet.
)";
}

// =============================================================================
// 11. TESTING
// =============================================================================

void runTests() {
    cout << "\n"
         << string(80, '=')
         << "\nSelf-tests\n"
         << string(80, '=')
         << '\n';

    {
        IPv4 address = IPv4::parse("192.168.1.10");

        if (address.toString() != "192.168.1.10") {
            throw runtime_error("IPv4 round-trip test failed.");
        }
    }

    {
        IPv4Network network =
            IPv4Network::parse("192.168.1.0/24");

        if (network.addressCount() != 256) {
            throw runtime_error("IPv4 address-count test failed.");
        }

        if (
            !network.contains(
                IPv4::parse("192.168.1.100")
            )
        ) {
            throw runtime_error("Network membership test failed.");
        }

        if (
            network.contains(
                IPv4::parse("192.168.2.1")
            )
        ) {
            throw runtime_error("Network exclusion test failed.");
        }
    }

    {
        if (
            classifyIPv4(
                IPv4::parse("10.1.2.3")
            ) != AddressCategory::Private
        ) {
            throw runtime_error("Private address classification failed.");
        }

        if (
            classifyIPv4(
                IPv4::parse("127.0.0.1")
            ) != AddressCategory::Loopback
        ) {
            throw runtime_error("Loopback classification failed.");
        }

        if (
            classifyIPv4(
                IPv4::parse("224.0.0.1")
            ) != AddressCategory::Multicast
        ) {
            throw runtime_error("Multicast classification failed.");
        }
    }

    {
        RoutingTable table;

        table.addRoute("0.0.0.0/0", "default");
        table.addRoute("10.0.0.0/8", "A");
        table.addRoute("10.1.0.0/16", "B");
        table.addRoute("10.1.2.0/24", "C");

        auto route =
            table.lookup(IPv4::parse("10.1.2.50"));

        if (!route.has_value() ||
            route->nextHop != "C") {
            throw runtime_error(
                "Longest-prefix match test failed."
            );
        }

        route =
            table.lookup(IPv4::parse("8.8.8.8"));

        if (!route.has_value() ||
            route->nextHop != "default") {
            throw runtime_error(
                "Default route test failed."
            );
        }
    }

    {
        IPAM ipam(
            IPv4Network::parse("10.100.0.0/16")
        );

        IPv4Network first =
            ipam.allocate(
                "A",
                24,
                "application"
            );

        IPv4Network second =
            ipam.allocate(
                "B",
                24,
                "database"
            );

        if (first.overlaps(second)) {
            throw runtime_error(
                "IPAM overlap test failed."
            );
        }
    }

    cout << "All C++ self-tests passed.\n";
}

// =============================================================================
// 12. MAIN
// =============================================================================

int main() {
    try {
        cout
            << "IP ADDRESSING ENTERPRISE CASE STUDY\n"
            << "C++17 implementation\n";

        demonstrateIPv4Fundamentals();
        demonstrateClassification();
        demonstrateSubnetting();
        demonstrateVLSM();
        demonstrateIPAM();
        demonstrateDHCP();
        demonstrateNAT();
        demonstrateRouting();
        demonstrateNetworkSecurity();
        demonstrateEdgeCases();
        runTests();

        cout << "\nProgram completed successfully.\n";
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
