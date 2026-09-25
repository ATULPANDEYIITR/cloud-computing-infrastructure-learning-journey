/*
 * SUBNETTING AND CIDR
 * ===================
 *
 * C++17 case study:
 * Enterprise IPv4 Address Allocation and Routing Simulator
 *
 * Scenario:
 * An organization owns 10.50.0.0/16 and needs to:
 *
 * 1. Allocate networks to departments using VLSM.
 * 2. Validate that allocations do not overlap.
 * 3. Calculate network, broadcast, and host ranges.
 * 4. Determine whether addresses belong to networks.
 * 5. Build a small routing table.
 * 6. Apply longest-prefix matching.
 * 7. Demonstrate route summarization.
 *
 * The program uses only the C++17 standard library.
 */

#include <algorithm>
#include <array>
#include <bitset>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

using IPv4 = std::uint32_t;

// ---------------------------------------------------------------------------
// BASIC IPv4 UTILITIES
// ---------------------------------------------------------------------------

std::array<int, 4> parseOctets(const std::string& address) {
    std::array<int, 4> octets{};
    std::stringstream stream(address);
    std::string token;
    int index = 0;

    while (std::getline(stream, token, '.')) {
        if (index >= 4 || token.empty()) {
            throw std::invalid_argument("Invalid IPv4 address: " + address);
        }

        for (char character : token) {
            if (!std::isdigit(static_cast<unsigned char>(character))) {
                throw std::invalid_argument(
                    "Invalid IPv4 octet: " + token
                );
            }
        }

        int value = std::stoi(token);

        if (value < 0 || value > 255) {
            throw std::invalid_argument(
                "IPv4 octet out of range: " + token
            );
        }

        octets[index++] = value;
    }

    if (index != 4) {
        throw std::invalid_argument("IPv4 requires four octets.");
    }

    return octets;
}

IPv4 parseIPv4(const std::string& address) {
    const auto octets = parseOctets(address);

    return
        (static_cast<IPv4>(octets[0]) << 24) |
        (static_cast<IPv4>(octets[1]) << 16) |
        (static_cast<IPv4>(octets[2]) << 8) |
        static_cast<IPv4>(octets[3]);
}

std::string ipv4ToString(IPv4 address) {
    std::ostringstream output;

    output
        << ((address >> 24) & 0xFF) << '.'
        << ((address >> 16) & 0xFF) << '.'
        << ((address >> 8) & 0xFF) << '.'
        << (address & 0xFF);

    return output.str();
}

std::string ipv4ToBinary(IPv4 address) {
    std::bitset<32> bits(address);
    std::string binary = bits.to_string();

    for (int position = 8; position < 32; position += 9) {
        binary.insert(position, ".");
    }

    return binary;
}

// ---------------------------------------------------------------------------
// CIDR REPRESENTATION
// ---------------------------------------------------------------------------

struct CIDRNetwork {
    IPv4 network;
    std::uint8_t prefix;

    IPv4 mask() const {
        if (prefix == 0) {
            return 0;
        }

        return static_cast<IPv4>(
            0xFFFFFFFFu << (32 - prefix)
        );
    }

    IPv4 wildcard() const {
        return ~mask();
    }

    IPv4 broadcast() const {
        return network | wildcard();
    }

    std::uint64_t totalAddresses() const {
        return std::uint64_t{1} << (32 - prefix);
    }

    std::uint64_t conventionalUsableHosts() const {
        if (prefix >= 31) {
            return 0;
        }

        return totalAddresses() - 2;
    }

    std::uint64_t specialAwareHosts() const {
        if (prefix == 31) {
            return 2;
        }

        if (prefix == 32) {
            return 1;
        }

        return conventionalUsableHosts();
    }

    bool contains(IPv4 address) const {
        return address >= network &&
               address <= broadcast();
    }

    bool contains(const CIDRNetwork& other) const {
        return other.network >= network &&
               other.broadcast() <= broadcast();
    }

    bool overlaps(const CIDRNetwork& other) const {
        return network <= other.broadcast() &&
               other.network <= broadcast();
    }

    std::string toString() const {
        return ipv4ToString(network) +
               "/" +
               std::to_string(prefix);
    }
};

// ---------------------------------------------------------------------------
// CIDR PARSING
// ---------------------------------------------------------------------------

CIDRNetwork parseCIDR(const std::string& cidr) {
    const std::size_t slash = cidr.find('/');

    if (slash == std::string::npos ||
        cidr.find('/', slash + 1) != std::string::npos) {
        throw std::invalid_argument(
            "CIDR must have exactly one '/': " + cidr
        );
    }

    const std::string addressPart = cidr.substr(0, slash);
    const std::string prefixPart = cidr.substr(slash + 1);

    if (prefixPart.empty()) {
        throw std::invalid_argument("CIDR prefix is missing.");
    }

    int prefix = std::stoi(prefixPart);

    if (prefix < 0 || prefix > 32) {
        throw std::invalid_argument(
            "CIDR prefix must be between 0 and 32."
        );
    }

    const IPv4 address = parseIPv4(addressPart);

    CIDRNetwork result{
        address,
        static_cast<std::uint8_t>(prefix)
    };

    // Canonicalize the network. Host bits are discarded.
    result.network = address & result.mask();

    return result;
}

// ---------------------------------------------------------------------------
// HOST RANGE
// ---------------------------------------------------------------------------

struct AddressRange {
    IPv4 network;
    IPv4 broadcast;
    std::optional<IPv4> firstHost;
    std::optional<IPv4> lastHost;
};

AddressRange calculateHostRange(const CIDRNetwork& network) {
    AddressRange result{
        network.network,
        network.broadcast(),
        std::nullopt,
        std::nullopt
    };

    if (network.prefix < 31) {
        result.firstHost = network.network + 1;
        result.lastHost = network.broadcast() - 1;
    } else if (network.prefix == 31) {
        // RFC 3021 permits both addresses on point-to-point links.
        result.firstHost = network.network;
        result.lastHost = network.broadcast();
    } else {
        // A /32 represents a single address rather than a conventional LAN.
        result.firstHost = network.network;
        result.lastHost = network.network;
    }

    return result;
}

// ---------------------------------------------------------------------------
// FIXED-LENGTH SUBNETTING
// ---------------------------------------------------------------------------

std::vector<CIDRNetwork> splitNetwork(
    const CIDRNetwork& parent,
    std::uint8_t childPrefix
) {
    if (childPrefix < parent.prefix) {
        throw std::invalid_argument(
            "Child prefix must be equal to or longer than parent prefix."
        );
    }

    if (childPrefix > 32) {
        throw std::invalid_argument("Prefix cannot exceed /32.");
    }

    const std::uint64_t count =
        std::uint64_t{1} << (childPrefix - parent.prefix);

    const std::uint64_t blockSize =
        std::uint64_t{1} << (32 - childPrefix);

    std::vector<CIDRNetwork> result;
    result.reserve(static_cast<std::size_t>(count));

    for (std::uint64_t index = 0; index < count; ++index) {
        const std::uint64_t address =
            static_cast<std::uint64_t>(parent.network) +
            index * blockSize;

        result.push_back({
            static_cast<IPv4>(address),
            childPrefix
        });
    }

    return result;
}

// ---------------------------------------------------------------------------
// VLSM
// ---------------------------------------------------------------------------

struct Requirement {
    std::string name;
    std::uint64_t hosts;
};

struct Allocation {
    Requirement requirement;
    CIDRNetwork network;
};

std::uint8_t prefixForHosts(std::uint64_t requiredHosts) {
    if (requiredHosts == 0) {
        throw std::invalid_argument(
            "Host requirement must be positive."
        );
    }

    for (int prefix = 30; prefix >= 0; --prefix) {
        const std::uint64_t total =
            std::uint64_t{1} << (32 - prefix);

        const std::uint64_t usable = total - 2;

        if (usable >= requiredHosts) {
            return static_cast<std::uint8_t>(prefix);
        }
    }

    throw std::invalid_argument(
        "Host requirement is too large for IPv4."
    );
}

std::vector<Allocation> allocateVLSM(
    const CIDRNetwork& parent,
    std::vector<Requirement> requirements
) {
    // Largest requirements are allocated first. This reduces fragmentation.
    std::sort(
        requirements.begin(),
        requirements.end(),
        [](const Requirement& left, const Requirement& right) {
            return left.hosts > right.hosts;
        }
    );

    std::vector<Allocation> allocations;

    std::uint64_t cursor = parent.network;

    for (const Requirement& requirement : requirements) {
        const std::uint8_t prefix =
            prefixForHosts(requirement.hosts);

        const std::uint64_t blockSize =
            std::uint64_t{1} << (32 - prefix);

        // CIDR blocks must start at an address aligned to their block size.
        const std::uint64_t remainder = cursor % blockSize;

        if (remainder != 0) {
            cursor += blockSize - remainder;
        }

        const std::uint64_t candidateNetwork = cursor;
        const std::uint64_t candidateBroadcast =
            candidateNetwork + blockSize - 1;

        if (
            candidateNetwork < parent.network ||
            candidateBroadcast > parent.broadcast()
        ) {
            throw std::runtime_error(
                "VLSM allocation does not fit inside parent network."
            );
        }

        CIDRNetwork network{
            static_cast<IPv4>(candidateNetwork),
            prefix
        };

        allocations.push_back({
            requirement,
            network
        });

        cursor = candidateBroadcast + 1;
    }

    return allocations;
}

// ---------------------------------------------------------------------------
// ROUTING
// ---------------------------------------------------------------------------

struct Route {
    CIDRNetwork network;
    std::string nextHop;
};

std::optional<Route> longestPrefixMatch(
    IPv4 destination,
    const std::vector<Route>& routes
) {
    std::optional<Route> best;

    for (const Route& route : routes) {
        if (!route.network.contains(destination)) {
            continue;
        }

        if (
            !best.has_value() ||
            route.network.prefix > best->network.prefix
        ) {
            best = route;
        }
    }

    return best;
}

// ---------------------------------------------------------------------------
// EXACT ROUTE SUMMARIZATION
// ---------------------------------------------------------------------------

std::optional<CIDRNetwork> summarizeTwo(
    const CIDRNetwork& first,
    const CIDRNetwork& second
) {
    IPv4 minimum = std::min(first.network, second.network);
    IPv4 maximum = std::max(
        first.broadcast(),
        second.broadcast()
    );

    IPv4 difference = minimum ^ maximum;

    std::uint8_t commonBits = 32;

    if (difference != 0) {
        commonBits = static_cast<std::uint8_t>(
            __builtin_clz(difference)
        );
    }

    const std::uint8_t prefix = commonBits;

    CIDRNetwork candidate{
        minimum,
        prefix
    };

    candidate.network &= candidate.mask();

    if (
        candidate.network == minimum &&
        candidate.broadcast() == maximum
    ) {
        return candidate;
    }

    return std::nullopt;
}

// ---------------------------------------------------------------------------
// DISPLAY FUNCTIONS
// ---------------------------------------------------------------------------

void printNetworkAnalysis(const CIDRNetwork& network) {
    const AddressRange range =
        calculateHostRange(network);

    std::cout << "\nNetwork: " << network.toString() << '\n';
    std::cout << std::string(70, '-') << '\n';

    std::cout
        << "Network address : "
        << ipv4ToString(range.network)
        << '\n';

    std::cout
        << "Subnet mask     : "
        << ipv4ToString(network.mask())
        << '\n';

    std::cout
        << "Wildcard mask   : "
        << ipv4ToString(network.wildcard())
        << '\n';

    std::cout
        << "Broadcast       : "
        << ipv4ToString(range.broadcast)
        << '\n';

    std::cout
        << "Total addresses : "
        << network.totalAddresses()
        << '\n';

    std::cout
        << "Usable hosts    : "
        << network.conventionalUsableHosts()
        << '\n';

    std::cout
        << "Special-aware   : "
        << network.specialAwareHosts()
        << '\n';

    std::cout
        << "Binary network  : "
        << ipv4ToBinary(network.network)
        << '\n';

    std::cout
        << "First host      : "
        << ipv4ToString(*range.firstHost)
        << '\n';

    std::cout
        << "Last host       : "
        << ipv4ToString(*range.lastHost)
        << '\n';
}

void printSubnets(
    const CIDRNetwork& parent,
    std::uint8_t childPrefix
) {
    const auto subnets =
        splitNetwork(parent, childPrefix);

    std::cout
        << "\n"
        << parent.toString()
        << " split into /"
        << static_cast<int>(childPrefix)
        << ":\n";

    std::cout << std::string(85, '-') << '\n';

    for (std::size_t index = 0; index < subnets.size(); ++index) {
        const auto& subnet = subnets[index];

        std::cout
            << std::setw(3)
            << index + 1
            << ". "
            << std::setw(18)
            << std::left
            << subnet.toString()
            << " network="
            << std::setw(15)
            << ipv4ToString(subnet.network)
            << " broadcast="
            << std::setw(15)
            << ipv4ToString(subnet.broadcast())
            << " hosts="
            << subnet.conventionalUsableHosts()
            << '\n';
    }
}

void printVLSM(
    const CIDRNetwork& parent,
    const std::vector<Allocation>& allocations
) {
    std::cout
        << "\nVLSM allocation for "
        << parent.toString()
        << '\n';

    std::cout << std::string(100, '-') << '\n';

    for (const auto& allocation : allocations) {
        const auto& network = allocation.network;

        std::cout
            << std::left
            << std::setw(18)
            << allocation.requirement.name
            << " requested="
            << std::setw(5)
            << allocation.requirement.hosts
            << " network="
            << std::setw(19)
            << network.toString()
            << " usable="
            << std::setw(5)
            << network.conventionalUsableHosts()
            << " range="
            << ipv4ToString(network.network)
            << " - "
            << ipv4ToString(network.broadcast())
            << '\n';
    }
}

void printRoutingDecision(
    const std::string& destination,
    const std::vector<Route>& routes
) {
    const IPv4 address = parseIPv4(destination);

    const auto selected =
        longestPrefixMatch(address, routes);

    std::cout << std::left
              << std::setw(18)
              << destination;

    if (selected.has_value()) {
        std::cout
            << " -> "
            << std::setw(18)
            << selected->network.toString()
            << " -> "
            << selected->nextHop
            << '\n';
    } else {
        std::cout << " -> no route\n";
    }
}

// ---------------------------------------------------------------------------
// VALIDATION
// ---------------------------------------------------------------------------

void require(
    bool condition,
    const std::string& message
) {
    if (!condition) {
        throw std::runtime_error(
            "Test failed: " + message
        );
    }
}

void runTests() {
    require(
        parseCIDR("192.168.10.77/26").network ==
            parseIPv4("192.168.10.64"),
        "network calculation"
    );

    require(
        parseCIDR("192.168.10.77/26").broadcast() ==
            parseIPv4("192.168.10.127"),
        "broadcast calculation"
    );

    require(
        parseCIDR("192.168.10.0/24").conventionalUsableHosts()
            == 254,
        "/24 host count"
    );

    require(
        parseCIDR("192.168.10.0/31").specialAwareHosts()
            == 2,
        "/31 host semantics"
    );

    require(
        parseCIDR("192.168.10.10/32").specialAwareHosts()
            == 1,
        "/32 host semantics"
    );

    const auto subnets =
        splitNetwork(
            parseCIDR("192.168.1.0/24"),
            26
        );

    require(
        subnets.size() == 4,
        "four /26 networks inside /24"
    );

    require(
        parseCIDR("10.0.0.0/8").contains(
            parseIPv4("10.20.30.40")
        ),
        "address membership"
    );

    require(
        parseCIDR("10.0.0.0/8").contains(
            parseCIDR("10.20.0.0/16")
        ),
        "network containment"
    );

    require(
        parseCIDR("192.168.0.0/24").overlaps(
            parseCIDR("192.168.0.128/25")
        ),
        "network overlap"
    );

    const std::vector<Route> routes{
        {parseCIDR("0.0.0.0/0"), "Internet"},
        {parseCIDR("10.0.0.0/8"), "Core-A"},
        {parseCIDR("10.20.0.0/16"), "Core-B"},
        {parseCIDR("10.20.30.0/24"), "Distribution-C"}
    };

    const auto route =
        longestPrefixMatch(
            parseIPv4("10.20.30.40"),
            routes
        );

    require(
        route.has_value() &&
        route->nextHop == "Distribution-C",
        "longest-prefix routing"
    );

    std::cout << "\nAll C++ tests passed.\n";
}

// ---------------------------------------------------------------------------
// MAIN CASE STUDY
// ---------------------------------------------------------------------------

int main() {
    try {
        std::cout << std::string(80, '=') << '\n';
        std::cout
            << "SUBNETTING AND CIDR - C++ ENTERPRISE CASE STUDY\n";
        std::cout << std::string(80, '=') << '\n';

        // -------------------------------------------------------------------
        // PART 1: Basic CIDR analysis
        // -------------------------------------------------------------------

        std::cout << "\n1. BASIC NETWORK ANALYSIS\n";

        const CIDRNetwork example =
            parseCIDR("192.168.10.77/26");

        printNetworkAnalysis(example);

        // -------------------------------------------------------------------
        // PART 2: Fixed-length subnetting
        // -------------------------------------------------------------------

        std::cout << "\n2. FIXED-LENGTH SUBNETTING\n";

        printSubnets(
            parseCIDR("192.168.50.0/24"),
            26
        );

        // -------------------------------------------------------------------
        // PART 3: VLSM enterprise allocation
        // -------------------------------------------------------------------

        std::cout << "\n3. VLSM ENTERPRISE DESIGN\n";

        const CIDRNetwork enterprise =
            parseCIDR("10.50.0.0/16");

        const std::vector<Requirement> requirements{
            {"Engineering", 500},
            {"Operations", 200},
            {"Guest-WiFi", 100},
            {"Servers", 60},
            {"Finance", 30},
            {"Network-P2P", 2}
        };

        const auto allocations =
            allocateVLSM(
                enterprise,
                requirements
            );

        printVLSM(
            enterprise,
            allocations
        );

        // Verify that no two allocations overlap.
        for (std::size_t i = 0; i < allocations.size(); ++i) {
            for (std::size_t j = i + 1;
                 j < allocations.size();
                 ++j) {

                require(
                    !allocations[i].network.overlaps(
                        allocations[j].network
                    ),
                    "VLSM allocations must not overlap"
                );
            }
        }

        // -------------------------------------------------------------------
        // PART 4: Address membership
        // -------------------------------------------------------------------

        std::cout << "\n4. ADDRESS MEMBERSHIP\n";

        const std::vector<std::string> addresses{
            "10.50.0.10",
            "10.50.10.10",
            "192.168.1.10"
        };

        for (const auto& address : addresses) {
            bool found = false;

            for (const auto& allocation : allocations) {
                if (allocation.network.contains(
                        parseIPv4(address))) {

                    std::cout
                        << std::setw(16)
                        << std::left
                        << address
                        << " belongs to "
                        << allocation.network.toString()
                        << " ("
                        << allocation.requirement.name
                        << ")\n";

                    found = true;
                    break;
                }
            }

            if (!found) {
                std::cout
                    << std::setw(16)
                    << std::left
                    << address
                    << " belongs to no enterprise subnet\n";
            }
        }

        // -------------------------------------------------------------------
        // PART 5: Routing table
        // -------------------------------------------------------------------

        std::cout << "\n5. LONGEST-PREFIX ROUTING\n";

        const std::vector<Route> routingTable{
            {
                parseCIDR("0.0.0.0/0"),
                "Internet Gateway"
            },
            {
                parseCIDR("10.0.0.0/8"),
                "Core Router A"
            },
            {
                parseCIDR("10.20.0.0/16"),
                "Core Router B"
            },
            {
                parseCIDR("10.20.30.0/24"),
                "Distribution Router C"
            },
            {
                parseCIDR("10.20.30.128/25"),
                "Access Router D"
            }
        };

        std::cout
            << std::setw(18)
            << std::left
            << "Destination"
            << " -> "
            << std::setw(18)
            << "Selected prefix"
            << " -> Next hop\n";

        std::cout << std::string(80, '-') << '\n';

        printRoutingDecision(
            "8.8.8.8",
            routingTable
        );

        printRoutingDecision(
            "10.1.2.3",
            routingTable
        );

        printRoutingDecision(
            "10.20.5.10",
            routingTable
        );

        printRoutingDecision(
            "10.20.30.25",
            routingTable
        );

        printRoutingDecision(
            "10.20.30.200",
            routingTable
        );

        // -------------------------------------------------------------------
        // PART 6: Route summarization
        // -------------------------------------------------------------------

        std::cout << "\n6. ROUTE SUMMARIZATION\n";

        const auto networkA =
            parseCIDR("192.168.0.0/25");

        const auto networkB =
            parseCIDR("192.168.0.128/25");

        const auto summary =
            summarizeTwo(
                networkA,
                networkB
            );

        std::cout
            << networkA.toString()
            << " + "
            << networkB.toString()
            << " -> ";

        if (summary.has_value()) {
            std::cout
                << summary->toString()
                << '\n';
        } else {
            std::cout
                << "cannot be represented by one exact CIDR block\n";
        }

        // -------------------------------------------------------------------
        // PART 7: Important edge cases
        // -------------------------------------------------------------------

        std::cout << "\n7. EDGE CASES\n";

        for (const std::string& cidr : {
                 "0.0.0.0/0",
                 "192.168.10.0/31",
                 "192.168.10.10/32"
             }) {

            printNetworkAnalysis(
                parseCIDR(cidr)
            );
        }

        // -------------------------------------------------------------------
        // PART 8: Verification
        // -------------------------------------------------------------------

        std::cout << "\n8. VERIFICATION\n";

        runTests();

        std::cout << "\nCase study completed successfully.\n";

        return 0;
    }
    catch (const std::exception& error) {
        std::cerr
            << "\nERROR: "
            << error.what()
            << '\n';

        return 1;
    }
}
