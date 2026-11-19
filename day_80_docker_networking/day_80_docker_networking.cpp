#include <algorithm>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

using namespace std;

/*
 * Docker Networking: C++17 Network Management Engine
 *
 * Implements:
 * - Bridge and host network drivers
 * - Custom IPv4 bridge subnets
 * - Container attachment and detachment
 * - IP address allocation
 * - DNS aliases
 * - Container communication
 * - Port publishing
 * - Network isolation
 * - Resource validation
 * - Network inspection
 *
 * No external dependencies.
 */

class NetworkError : public runtime_error {
public:
    using runtime_error::runtime_error;
};

class ValidationError : public NetworkError {
public:
    using NetworkError::NetworkError;
};

class AddressConflictError : public NetworkError {
public:
    using NetworkError::NetworkError;
};

enum class Driver {
    Bridge,
    Host
};

enum class ContainerState {
    Running,
    Stopped
};

struct IPv4 {
    uint32_t value{};

    static IPv4 parse(const string& text) {
        stringstream stream(text);
        string part;
        uint32_t result = 0;

        for (int i = 0; i < 4; ++i) {
            if (!getline(stream, part, '.')) {
                throw ValidationError("Invalid IPv4 address.");
            }

            if (part.empty() || part.size() > 3) {
                throw ValidationError("Invalid IPv4 octet.");
            }

            if (part.size() > 1 && part[0] == '0') {
                throw ValidationError("Leading zeroes are not allowed.");
            }

            int octet;

            try {
                size_t consumed = 0;
                octet = stoi(part, &consumed);

                if (consumed != part.size()) {
                    throw ValidationError("Invalid IPv4 octet.");
                }
            } catch (const exception&) {
                throw ValidationError("Invalid IPv4 octet.");
            }

            if (octet < 0 || octet > 255) {
                throw ValidationError("IPv4 octet out of range.");
            }

            result = (result << 8) | static_cast<uint32_t>(octet);
        }

        if (getline(stream, part, '.')) {
            throw ValidationError("Too many IPv4 octets.");
        }

        return IPv4{result};
    }

    string str() const {
        return to_string((value >> 24) & 255) + "." +
               to_string((value >> 16) & 255) + "." +
               to_string((value >> 8) & 255) + "." +
               to_string(value & 255);
    }
};

struct Subnet {
    IPv4 network;
    uint32_t mask;
    int prefix;

    static Subnet parse(const string& cidr) {
        size_t separator = cidr.find('/');

        if (separator == string::npos) {
            throw ValidationError("CIDR prefix is required.");
        }

        IPv4 address = IPv4::parse(cidr.substr(0, separator));

        int prefix;

        try {
            prefix = stoi(cidr.substr(separator + 1));
        } catch (const exception&) {
            throw ValidationError("Invalid CIDR prefix.");
        }

        if (prefix < 16 || prefix > 30) {
            throw ValidationError(
                "This simulator supports prefixes /16 through /30."
            );
        }

        uint32_t mask = 0xFFFFFFFFu << (32 - prefix);
        uint32_t network = address.value & mask;

        if (network != address.value) {
            throw ValidationError(
                "CIDR address must be the network address."
            );
        }

        return Subnet{IPv4{network}, mask, prefix};
    }

    bool contains(IPv4 address) const {
        return (address.value & mask) == network.value;
    }

    bool overlaps(const Subnet& other) const {
        return (network.value & other.mask) == other.network.value ||
               (other.network.value & mask) == network.value;
    }

    uint32_t broadcast() const {
        return network.value | ~mask;
    }
};

struct PortBinding {
    int containerPort;
    int hostPort;
    string protocol;

    void validate() const {
        if (containerPort < 1 || containerPort > 65535 ||
            hostPort < 1 || hostPort > 65535) {
            throw ValidationError("Invalid port number.");
        }

        if (protocol != "tcp" && protocol != "udp") {
            throw ValidationError("Invalid transport protocol.");
        }
    }
};

struct Container {
    string name;
    string image;
    map<int, string> ports;
    ContainerState state{ContainerState::Running};
    set<string> networks;
};

struct Network {
    string name;
    Driver driver;
    optional<Subnet> subnet;
    optional<IPv4> gateway;
    uint32_t nextAddress{};
    map<string, IPv4> addresses;
    map<string, string> aliases;
};

class DockerEngine {
private:
    map<string, Container> containers;
    map<string, Network> networks;

    map<tuple<int, string>, string> publishedPorts;

    static bool validName(const string& name) {
        return !name.empty() &&
               all_of(name.begin(), name.end(), [](unsigned char c) {
                   return isalnum(c) || c == '-' || c == '_' || c == '.';
               });
    }

    void validatePortConfiguration(
        const map<int, string>& ports
    ) const {
        for (const auto& [port, protocol] : ports) {
            if (port < 1 || port > 65535) {
                throw ValidationError("Invalid container port.");
            }

            if (protocol != "tcp" && protocol != "udp") {
                throw ValidationError("Invalid protocol.");
            }
        }
    }

    IPv4 allocateAddress(Network& network) {
        if (!network.subnet) {
            throw ValidationError("Network has no subnet.");
        }

        const Subnet& subnet = *network.subnet;

        while (network.nextAddress < subnet.broadcast()) {
            IPv4 candidate{network.nextAddress++};

            if (candidate == *network.gateway) {
                continue;
            }

            bool used = false;

            for (const auto& [name, address] : network.addresses) {
                if (address.value == candidate.value) {
                    used = true;
                    break;
                }
            }

            if (!used) {
                return candidate;
            }
        }

        throw AddressConflictError("Subnet address pool exhausted.");
    }

public:
    void createNetwork(
        const string& name,
        Driver driver,
        const string& cidr = "172.20.0.0/24"
    ) {
        if (!validName(name)) {
            throw ValidationError("Invalid network name.");
        }

        if (networks.count(name)) {
            throw ValidationError("Network already exists.");
        }

        Network network;
        network.name = name;
        network.driver = driver;

        if (driver == Driver::Bridge) {
            Subnet subnet = Subnet::parse(cidr);

            for (const auto& [existingName, existing] : networks) {
                if (
                    existing.subnet &&
                    subnet.overlaps(*existing.subnet)
                ) {
                    throw AddressConflictError(
                        "Overlapping subnet with " + existingName
                    );
                }
            }

            network.subnet = subnet;
            network.gateway = IPv4{subnet.network.value + 1};
            network.nextAddress = subnet.network.value + 2;
        }

        networks.emplace(name, move(network));

        cout << "Network created: " << name << '\n';
    }

    void createContainer(
        const string& name,
        const string& image,
        map<int, string> ports
    ) {
        if (!validName(name) || image.empty()) {
            throw ValidationError("Invalid container configuration.");
        }

        if (containers.count(name)) {
            throw ValidationError("Container already exists.");
        }

        validatePortConfiguration(ports);

        containers.emplace(
            name,
            Container{name, image, move(ports)}
        );

        cout << "Container created: " << name << '\n';
    }

    void connect(
        const string& containerName,
        const string& networkName,
        const vector<string>& aliases = {}
    ) {
        auto containerIt = containers.find(containerName);
        auto networkIt = networks.find(networkName);

        if (
            containerIt == containers.end() ||
            networkIt == networks.end()
        ) {
            throw ValidationError("Unknown container or network.");
        }

        Container& container = containerIt->second;
        Network& network = networkIt->second;

        if (container.state != ContainerState::Running) {
            throw NetworkError("Stopped containers cannot connect.");
        }

        if (container.networks.count(networkName)) {
            throw ValidationError("Already connected.");
        }

        if (network.driver == Driver::Bridge) {
            for (const string& alias : aliases) {
                if (alias.empty()) {
                    throw ValidationError("Empty DNS alias.");
                }

                if (network.aliases.count(alias)) {
                    throw ValidationError("Duplicate DNS alias.");
                }
            }

            IPv4 address = allocateAddress(network);

            network.addresses[containerName] = address;
            network.aliases[containerName] = containerName;

            for (const string& alias : aliases) {
                network.aliases[alias] = containerName;
            }

            cout << containerName << " assigned "
                 << address.str() << " on " << networkName << '\n';
        }

        container.networks.insert(networkName);
    }

    void disconnect(
        const string& containerName,
        const string& networkName
    ) {
        auto& container = containers.at(containerName);
        auto& network = networks.at(networkName);

        if (network.driver == Driver::Host) {
            throw NetworkError(
                "Host network cannot be detached independently."
            );
        }

        if (!container.networks.count(networkName)) {
            throw ValidationError("Container is not attached.");
        }

        network.addresses.erase(containerName);

        for (auto it = network.aliases.begin();
             it != network.aliases.end();) {
            if (it->second == containerName) {
                it = network.aliases.erase(it);
            } else {
                ++it;
            }
        }

        container.networks.erase(networkName);
    }

    string resolve(
        const string& sourceName,
        const string& alias,
        const string& networkName
    ) const {
        const auto& source = containers.at(sourceName);
        const auto& network = networks.at(networkName);

        if (network.driver != Driver::Bridge) {
            throw NetworkError("Bridge DNS unavailable.");
        }

        if (!source.networks.count(networkName)) {
            throw NetworkError("Source is not connected.");
        }

        auto aliasIt = network.aliases.find(alias);

        if (aliasIt == network.aliases.end()) {
            throw NetworkError("DNS name not found.");
        }

        return network.addresses.at(aliasIt->second).str();
    }

    bool canCommunicate(
        const string& sourceName,
        const string& destinationName,
        const string& networkName,
        int destinationPort
    ) const {
        const auto& source = containers.at(sourceName);
        const auto& destination = containers.at(destinationName);
        const auto& network = networks.at(networkName);

        if (
            source.state != ContainerState::Running ||
            destination.state != ContainerState::Running
        ) {
            return false;
        }

        if (!destination.ports.count(destinationPort)) {
            return false;
        }

        if (
            !source.networks.count(networkName) ||
            !destination.networks.count(networkName)
        ) {
            return false;
        }

        if (network.driver == Driver::Host) {
            return true;
        }

        return network.addresses.count(sourceName) &&
               network.addresses.count(destinationName);
    }

    void publishPort(
        const string& containerName,
        const PortBinding& binding
    ) {
        binding.validate();

        const auto& container = containers.at(containerName);

        if (!container.ports.count(binding.containerPort)) {
            throw ValidationError("Container port is not declared.");
        }

        auto key = make_tuple(binding.hostPort, binding.protocol);

        if (publishedPorts.count(key)) {
            throw AddressConflictError("Host port already published.");
        }

        publishedPorts[key] = containerName;

        cout << "Published " << binding.hostPort
             << " -> " << containerName << ':'
             << binding.containerPort << '/' << binding.protocol
             << '\n';
    }

    void stopContainer(const string& name) {
        auto& container = containers.at(name);
        container.state = ContainerState::Stopped;

        for (auto it = publishedPorts.begin();
             it != publishedPorts.end();) {
            if (it->second == name) {
                it = publishedPorts.erase(it);
            } else {
                ++it;
            }
        }
    }

    void inspectNetwork(const string& name) const {
        const auto& network = networks.at(name);

        cout << "\nNetwork: " << network.name << '\n';
        cout << "Driver: "
             << (network.driver == Driver::Bridge ? "bridge" : "host")
             << '\n';

        if (network.subnet) {
            cout << "Subnet: "
                 << network.subnet->network.str()
                 << '/' << network.subnet->prefix << '\n';

            cout << "Gateway: "
                 << network.gateway->str() << '\n';
        }

        for (const auto& [container, address] : network.addresses) {
            cout << "  " << container << ": "
                 << address.str() << '\n';
        }
    }

    void report() const {
        cout << "\nPublished ports:\n";

        for (const auto& [key, container] : publishedPorts) {
            cout << get<0>(key) << '/'
                 << get<1>(key) << " -> "
                 << container << '\n';
        }

        cout << "\nContainer network memberships:\n";

        for (const auto& [name, container] : containers) {
            cout << name << ": ";

            for (const string& network : container.networks) {
                cout << network << ' ';
            }

            cout << '\n';
        }
    }
};

int main() {
    try {
        DockerEngine engine;

        engine.createNetwork(
            "frontend",
            Driver::Bridge,
            "172.20.0.0/24"
        );

        engine.createNetwork(
            "backend",
            Driver::Bridge,
            "172.21.0.0/24"
        );

        engine.createNetwork(
            "host-network",
            Driver::Host
        );

        engine.createContainer(
            "web",
            "nginx:1.27",
            {{80, "tcp"}}
        );

        engine.createContainer(
            "api",
            "python:3.13",
            {{8000, "tcp"}}
        );

        engine.createContainer(
            "database",
            "postgres:18",
            {{5432, "tcp"}}
        );

        engine.connect("web", "frontend");
        engine.connect("api", "frontend", {"api-service"});
        engine.connect("api", "backend");
        engine.connect("database", "backend", {"db"});

        engine.connect("web", "host-network");

        string address = engine.resolve(
            "web",
            "api-service",
            "frontend"
        );

        cout << "\nAPI DNS address: " << address << '\n';

        if (
            !engine.canCommunicate(
                "web", "api", "frontend", 8000
            )
        ) {
            throw NetworkError("Expected API connectivity.");
        }

        if (
            engine.canCommunicate(
                "web", "database", "frontend", 5432
            )
        ) {
            throw NetworkError("Network isolation was violated.");
        }

        if (
            !engine.canCommunicate(
                "api", "database", "backend", 5432
            )
        ) {
            throw NetworkError("Database connectivity failed.");
        }

        engine.publishPort(
            "web",
            PortBinding{80, 8080, "tcp"}
        );

        engine.inspectNetwork("frontend");
        engine.inspectNetwork("backend");
        engine.report();

        engine.stopContainer("web");

        if (
            engine.canCommunicate(
                "web", "api", "frontend", 8000
            )
        ) {
            throw NetworkError("Stopped container communicated.");
        }

        // Invalid subnet overlap must be rejected.
        try {
            engine.createNetwork(
                "invalid-network",
                Driver::Bridge,
                "172.20.0.0/25"
            );

            throw NetworkError("Subnet overlap was accepted.");
        } catch (const AddressConflictError&) {
            cout << "\nOverlapping subnet correctly rejected.\n";
        }

        cout << "\nAll Docker networking tests passed.\n";

    } catch (const exception& error) {
        cerr << "Error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
