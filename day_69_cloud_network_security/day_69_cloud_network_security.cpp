#include <algorithm>
#include <cstdint>
#include <exception>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

using namespace std;

enum class Direction {
    Inbound,
    Outbound
};

enum class Action {
    Allow,
    Deny
};

enum class Protocol {
    TCP,
    UDP,
    ICMP,
    ALL
};

enum class Decision {
    Allow,
    Deny
};

string toString(Decision decision) {
    return decision == Decision::Allow ? "ALLOW" : "DENY";
}

string toString(Action action) {
    return action == Action::Allow ? "ALLOW" : "DENY";
}

uint32_t parseIPv4(const string& address) {
    stringstream stream(address);
    string part;
    uint32_t result = 0;
    int count = 0;

    while (getline(stream, part, '.')) {
        if (part.empty() || part.size() > 3) {
            throw invalid_argument("Invalid IPv4 address");
        }

        size_t consumed = 0;
        int octet = stoi(part, &consumed);

        if (consumed != part.size() || octet < 0 || octet > 255) {
            throw invalid_argument("Invalid IPv4 octet");
        }

        result = (result << 8) | static_cast<uint32_t>(octet);
        ++count;
    }

    if (count != 4) {
        throw invalid_argument("IPv4 requires four octets");
    }

    return result;
}

struct CIDR {
    uint32_t network;
    uint32_t mask;

    explicit CIDR(const string& value) {
        size_t slash = value.find('/');

        if (slash == string::npos) {
            throw invalid_argument("CIDR prefix is required");
        }

        uint32_t address = parseIPv4(value.substr(0, slash));
        int prefix = stoi(value.substr(slash + 1));

        if (prefix < 0 || prefix > 32) {
            throw invalid_argument("Invalid CIDR prefix");
        }

        mask = prefix == 0
            ? 0
            : (0xFFFFFFFFu << (32 - prefix));

        network = address & mask;
    }

    bool contains(const string& address) const {
        return (parseIPv4(address) & mask) == network;
    }
};

struct Packet {
    string sourceIP;
    string destinationIP;
    Protocol protocol;
    uint16_t sourcePort = 0;
    uint16_t destinationPort = 0;

    void validate() const {
        parseIPv4(sourceIP);
        parseIPv4(destinationIP);

        if (
            (protocol == Protocol::ICMP || protocol == Protocol::ALL) &&
            (sourcePort != 0 || destinationPort != 0)
        ) {
            throw invalid_argument(
                "ICMP and ALL packets must use zero ports"
            );
        }
    }
};

struct Rule {
    string id;
    Direction direction;
    Action action;
    Protocol protocol;
    CIDR network;
    uint16_t portStart;
    uint16_t portEnd;
    int priority;
    string description;

    Rule(
        string ruleId,
        Direction ruleDirection,
        Action ruleAction,
        Protocol ruleProtocol,
        const string& cidr,
        uint16_t start = 0,
        uint16_t end = 65535,
        int rulePriority = 100,
        string ruleDescription = ""
    )
        : id(move(ruleId)),
          direction(ruleDirection),
          action(ruleAction),
          protocol(ruleProtocol),
          network(cidr),
          portStart(start),
          portEnd(end),
          priority(rulePriority),
          description(move(ruleDescription)) {

        if (id.empty()) {
            throw invalid_argument("Rule ID cannot be empty");
        }

        if (portStart > portEnd || priority < 0) {
            throw invalid_argument("Invalid rule range or priority");
        }

        if (
            (protocol == Protocol::ICMP || protocol == Protocol::ALL) &&
            (portStart != 0 || portEnd != 65535)
        ) {
            throw invalid_argument(
                "ICMP and ALL rules must use the full port range"
            );
        }
    }

    bool matches(
        const Packet& packet,
        Direction requestedDirection
    ) const {

        if (direction != requestedDirection) return false;

        const string& address =
            direction == Direction::Inbound
            ? packet.sourceIP
            : packet.destinationIP;

        if (!network.contains(address)) return false;

        if (
            protocol != Protocol::ALL &&
            protocol != packet.protocol
        ) {
            return false;
        }

        if (
            packet.protocol == Protocol::ICMP ||
            packet.protocol == Protocol::ALL
        ) {
            return true;
        }

        return packet.destinationPort >= portStart &&
               packet.destinationPort <= portEnd;
    }
};

struct Evaluation {
    Decision decision;
    string layer;
    string reason;
    string ruleId;
};

using ConnectionKey = tuple<
    string, string, Protocol, uint16_t, uint16_t
>;

ConnectionKey connectionKey(const Packet& packet) {
    return {
        packet.sourceIP,
        packet.destinationIP,
        packet.protocol,
        packet.sourcePort,
        packet.destinationPort
    };
}

ConnectionKey reverseKey(const Packet& packet) {
    return {
        packet.destinationIP,
        packet.sourceIP,
        packet.protocol,
        packet.destinationPort,
        packet.sourcePort
    };
}

class ConnectionTracker {
private:
    set<ConnectionKey> established;

public:
    bool contains(const Packet& packet) const {
        return established.count(connectionKey(packet)) ||
               established.count(reverseKey(packet));
    }

    void add(const Packet& packet) {
        established.insert(connectionKey(packet));
    }

    size_t size() const {
        return established.size();
    }
};

class SecurityGroup {
private:
    string name;
    vector<Rule> rules;
    ConnectionTracker tracker;

public:
    explicit SecurityGroup(string groupName)
        : name(move(groupName)) {}

    void addRule(const Rule& rule) {
        if (rule.action != Action::Allow) {
            throw invalid_argument(
                "Security groups support ALLOW rules only"
            );
        }

        auto duplicate = find_if(
            rules.begin(),
            rules.end(),
            [&](const Rule& existing) {
                return existing.id == rule.id;
            }
        );

        if (duplicate != rules.end()) {
            throw invalid_argument("Duplicate security group rule");
        }

        rules.push_back(rule);
    }

    Evaluation inspect(
        const Packet& packet,
        Direction direction
    ) {

        if (tracker.contains(packet)) {
            return {
                Decision::Allow,
                name,
                "Established connection",
                ""
            };
        }

        for (const auto& rule : rules) {
            if (rule.matches(packet, direction)) {
                if (direction == Direction::Outbound) {
                    tracker.add(packet);
                }

                return {
                    Decision::Allow,
                    name,
                    "Explicit security group permission",
                    rule.id
                };
            }
        }

        return {
            Decision::Deny,
            name,
            "No matching allow rule",
            ""
        };
    }

    size_t ruleCount() const {
        return rules.size();
    }
};

class NetworkACL {
private:
    string name;
    vector<Rule> rules;

public:
    explicit NetworkACL(string aclName)
        : name(move(aclName)) {}

    void addRule(const Rule& rule) {
        if (any_of(
            rules.begin(),
            rules.end(),
            [&](const Rule& existing) {
                return existing.id == rule.id;
            }
        )) {
            throw invalid_argument("Duplicate ACL rule ID");
        }

        rules.push_back(rule);

        stable_sort(
            rules.begin(),
            rules.end(),
            [](const Rule& a, const Rule& b) {
                return a.priority < b.priority;
            }
        );
    }

    Evaluation inspect(
        const Packet& packet,
        Direction direction
    ) const {

        for (const auto& rule : rules) {
            if (rule.matches(packet, direction)) {
                return {
                    rule.action == Action::Allow
                        ? Decision::Allow
                        : Decision::Deny,
                    name,
                    "Matched ordered ACL rule",
                    rule.id
                };
            }
        }

        return {
            Decision::Deny,
            name,
            "Default deny",
            ""
        };
    }

    size_t ruleCount() const {
        return rules.size();
    }
};

class Firewall {
private:
    string name;
    vector<Rule> rules;
    ConnectionTracker tracker;

public:
    explicit Firewall(string firewallName)
        : name(move(firewallName)) {}

    void addRule(const Rule& rule) {
        if (any_of(
            rules.begin(),
            rules.end(),
            [&](const Rule& existing) {
                return existing.id == rule.id;
            }
        )) {
            throw invalid_argument("Duplicate firewall rule ID");
        }

        rules.push_back(rule);

        stable_sort(
            rules.begin(),
            rules.end(),
            [](const Rule& a, const Rule& b) {
                return a.priority < b.priority;
            }
        );
    }

    Evaluation inspect(
        const Packet& packet,
        Direction direction
    ) {

        if (tracker.contains(packet)) {
            return {
                Decision::Allow,
                name,
                "Established firewall connection",
                ""
            };
        }

        for (const auto& rule : rules) {
            if (rule.matches(packet, direction)) {
                if (
                    rule.action == Action::Allow &&
                    direction == Direction::Inbound
                ) {
                    tracker.add(packet);
                }

                return {
                    rule.action == Action::Allow
                        ? Decision::Allow
                        : Decision::Deny,
                    name,
                    "First matching firewall rule",
                    rule.id
                };
            }
        }

        return {
            Decision::Deny,
            name,
            "Firewall default deny",
            ""
        };
    }

    size_t ruleCount() const {
        return rules.size();
    }
};

class CloudSecurityEngine {
private:
    SecurityGroup securityGroup;
    NetworkACL networkACL;
    Firewall firewall;

public:
    CloudSecurityEngine(
        SecurityGroup sg,
        NetworkACL acl,
        Firewall fw
    )
        : securityGroup(move(sg)),
          networkACL(move(acl)),
          firewall(move(fw)) {}

    Evaluation inspect(
        const Packet& packet,
        Direction direction
    ) {

        packet.validate();

        vector<Evaluation> results;

        results.push_back(networkACL.inspect(packet, direction));
        results.push_back(securityGroup.inspect(packet, direction));
        results.push_back(firewall.inspect(packet, direction));

        for (const auto& result : results) {
            cout << "  " << result.layer
                 << ": " << toString(result.decision)
                 << " | " << result.reason << '\n';

            if (result.decision == Decision::Deny) {
                return result;
            }
        }

        return {
            Decision::Allow,
            "CloudSecurityEngine",
            "All layers permitted traffic",
            ""
        };
    }

    void audit() const {
        cout << "\nPOLICY AUDIT\n";
        cout << "Security group rules: "
             << securityGroup.ruleCount() << '\n';
        cout << "Network ACL rules: "
             << networkACL.ruleCount() << '\n';
        cout << "Firewall rules: "
             << firewall.ruleCount() << '\n';
    }
};

CloudSecurityEngine buildEnvironment() {
    SecurityGroup sg("application-sg");

    sg.addRule(Rule(
        "sg-https",
        Direction::Inbound,
        Action::Allow,
        Protocol::TCP,
        "0.0.0.0/0",
        443,
        443
    ));

    sg.addRule(Rule(
        "sg-db",
        Direction::Outbound,
        Action::Allow,
        Protocol::TCP,
        "10.0.2.0/24",
        5432,
        5432
    ));

    NetworkACL acl("application-acl");

    acl.addRule(Rule(
        "acl-https",
        Direction::Inbound,
        Action::Allow,
        Protocol::TCP,
        "0.0.0.0/0",
        443,
        443,
        100
    ));

    acl.addRule(Rule(
        "acl-return",
        Direction::Outbound,
        Action::Allow,
        Protocol::TCP,
        "0.0.0.0/0",
        0,
        65535,
        100
    ));

    Firewall firewall("edge-firewall");

    firewall.addRule(Rule(
        "fw-block",
        Direction::Inbound,
        Action::Deny,
        Protocol::ALL,
        "198.51.100.0/24",
        0,
        65535,
        10
    ));

    firewall.addRule(Rule(
        "fw-https",
        Direction::Inbound,
        Action::Allow,
        Protocol::TCP,
        "0.0.0.0/0",
        443,
        443,
        100
    ));

    firewall.addRule(Rule(
        "fw-outbound",
        Direction::Outbound,
        Action::Allow,
        Protocol::ALL,
        "0.0.0.0/0"
    ));

    return CloudSecurityEngine(
        move(sg),
        move(acl),
        move(firewall)
    );
}

int main() {
    try {
        auto engine = buildEnvironment();

        Packet https{
            "203.0.113.10",
            "10.0.0.10",
            Protocol::TCP,
            51000,
            443
        };

        Packet malicious{
            "198.51.100.20",
            "10.0.0.10",
            Protocol::TCP,
            51000,
            443
        };

        Packet unauthorized{
            "203.0.113.20",
            "10.0.0.10",
            Protocol::TCP,
            51000,
            22
        };

        cout << "CLOUD NETWORK SECURITY ENGINE\n";
        cout << "==============================\n";

        auto accepted = engine.inspect(
            https,
            Direction::Inbound
        );

        cout << "HTTPS result: "
             << toString(accepted.decision) << "\n\n";

        if (accepted.decision != Decision::Allow) {
            throw runtime_error("HTTPS test failed");
        }

        auto blocked = engine.inspect(
            malicious,
            Direction::Inbound
        );

        cout << "Malicious traffic: "
             << toString(blocked.decision) << "\n\n";

        if (blocked.decision != Decision::Deny) {
            throw runtime_error("Malicious traffic test failed");
        }

        auto rejected = engine.inspect(
            unauthorized,
            Direction::Inbound
        );

        cout << "Unauthorized SSH: "
             << toString(rejected.decision) << "\n\n";

        if (rejected.decision != Decision::Deny) {
            throw runtime_error("SSH test failed");
        }

        engine.audit();

        cout << "\nAll security tests passed.\n";
        return 0;

    } catch (const exception& error) {
        cerr << "Security engine error: "
             << error.what() << '\n';
        return 1;
    }
}
