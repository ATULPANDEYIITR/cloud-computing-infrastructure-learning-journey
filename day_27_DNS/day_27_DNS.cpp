/*
 * DNS: Hierarchy, Recursive Resolution, Authoritative Servers,
 *     DNS Records, and Caching
 *
 * C++17 industry-style case study:
 *
 * A simulated DNS infrastructure is implemented for a small service
 * platform. The system models:
 *
 *   Client
 *      |
 *      v
 *   Recursive Resolver
 *      |
 *      +---- Cache
 *      |
 *      +---- Root
 *      |
 *      +---- TLD
 *      |
 *      +---- Authoritative Server
 *
 * The implementation demonstrates:
 * - DNS names and normalization
 * - DNS resource records
 * - Zones
 * - Root and TLD referrals
 * - Authoritative data
 * - Iterative resolution
 * - Recursive resolution
 * - TTL-based caching
 * - Negative caching
 * - CNAME processing
 * - Query statistics
 * - Validation
 * - Failure conditions
 * - Complexity considerations
 *
 * Compile:
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic dns_case_study.cpp -o dns_case_study
 */

#include <algorithm>
#include <chrono>
#include <cctype>
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

using namespace std;


// ============================================================================
// 1. BASIC UTILITIES
// ============================================================================

void section(const string& title) {
    cout << "\n" << string(78, '=') << "\n";
    cout << title << "\n";
    cout << string(78, '=') << "\n";
}

string toLower(string value) {
    transform(
        value.begin(),
        value.end(),
        value.begin(),
        [](unsigned char character) {
            return static_cast<char>(tolower(character));
        }
    );

    return value;
}

string normalizeName(string name) {
    if (name.empty()) {
        throw invalid_argument(
            "DNS name cannot be empty."
        );
    }

    name = toLower(name);

    if (name.back() != '.') {
        name.push_back('.');
    }

    return name;
}

bool validateDnsName(const string& input) {
    if (input.empty()) {
        return false;
    }

    string name;

    try {
        name = normalizeName(input);
    } catch (...) {
        return false;
    }

    if (name == ".") {
        return true;
    }

    if (name.size() > 253) {
        return false;
    }

    if (name.back() == '.') {
        name.pop_back();
    }

    stringstream stream(name);
    string label;

    while (getline(stream, label, '.')) {
        if (label.empty() || label.size() > 63) {
            return false;
        }

        if (label.front() == '-' ||
            label.back() == '-') {
            return false;
        }

        for (unsigned char character : label) {
            if (!(isalnum(character) || character == '-')) {
                return false;
            }
        }
    }

    return true;
}

bool isSubdomain(
    const string& name,
    const string& zone
) {
    const string normalizedName = normalizeName(name);
    const string normalizedZone = normalizeName(zone);

    if (normalizedZone == ".") {
        return true;
    }

    return normalizedName == normalizedZone ||
           normalizedName.size() > normalizedZone.size() &&
           normalizedName.compare(
               normalizedName.size() - normalizedZone.size(),
               normalizedZone.size(),
               normalizedZone
           ) == 0;
}


// ============================================================================
// 2. DNS RESOURCE RECORD
// ============================================================================

struct DNSRecord {
    string name;
    string type;
    string value;
    int ttl;
    optional<int> priority;

    DNSRecord(
        string recordName,
        string recordType,
        string recordValue,
        int recordTtl,
        optional<int> recordPriority = nullopt
    )
        : name(normalizeName(move(recordName))),
          type(toLower(move(recordType))),
          value(move(recordValue)),
          ttl(recordTtl),
          priority(recordPriority) {

        if (ttl < 0) {
            throw invalid_argument(
                "TTL cannot be negative."
            );
        }
    }

    string toString() const {
        stringstream output;

        output
            << name << " "
            << ttl
            << " IN "
            << type
            << " "
            << value;

        if (priority.has_value()) {
            output
                << " priority="
                << *priority;
        }

        return output.str();
    }
};


// ============================================================================
// 3. DNS QUERY RESULT
// ============================================================================

struct DNSAnswer {
    string name;
    string type;
    vector<DNSRecord> records;

    bool authoritative = false;
    bool negative = false;

    string referralZone;
    vector<string> referralServers;

    bool hasReferral() const {
        return !referralZone.empty() &&
               !referralServers.empty();
    }
};


// ============================================================================
// 4. DNS ZONE
// ============================================================================

class DNSZone {
private:
    string origin;

    /*
     * A map is used because DNS queries naturally identify a record set
     * by owner name and record type.
     *
     * Key complexity:
     *   std::map -> O(log n)
     *
     * A production resolver may use hash tables or specialized trees for
     * different performance characteristics.
     */
    map<pair<string, string>, vector<DNSRecord>> records;

public:
    explicit DNSZone(string zoneOrigin)
        : origin(normalizeName(move(zoneOrigin))) {}

    const string& getOrigin() const {
        return origin;
    }

    void addRecord(const DNSRecord& record) {
        records[
            {record.name, record.type}
        ].push_back(record);
    }

    vector<DNSRecord> query(
        const string& name,
        const string& type
    ) const {
        const auto key = make_pair(
            normalizeName(name),
            toLower(type)
        );

        auto iterator = records.find(key);

        if (iterator == records.end()) {
            return {};
        }

        return iterator->second;
    }

    bool hasName(const string& name) const {
        const string normalizedName =
            normalizeName(name);

        for (const auto& [key, recordSet] : records) {
            if (key.first == normalizedName) {
                return true;
            }
        }

        return false;
    }

    void print() const {
        cout
            << "Zone: "
            << origin
            << "\n";

        for (const auto& [key, recordSet] : records) {
            for (const auto& record : recordSet) {
                cout
                    << "  "
                    << record.toString()
                    << "\n";
            }
        }
    }
};


// ============================================================================
// 5. SERVER ROLES
// ============================================================================

enum class ServerRole {
    ROOT,
    TLD,
    AUTHORITATIVE,
    RECURSIVE
};

string roleToString(ServerRole role) {
    switch (role) {
        case ServerRole::ROOT:
            return "Root";
        case ServerRole::TLD:
            return "TLD";
        case ServerRole::AUTHORITATIVE:
            return "Authoritative";
        case ServerRole::RECURSIVE:
            return "Recursive";
    }

    return "Unknown";
}

struct DNSServer {
    string name;
    ServerRole role;
    vector<string> zones;

    DNSServer(
        string serverName,
        ServerRole serverRole,
        vector<string> serverZones = {}
    )
        : name(normalizeName(move(serverName))),
          role(serverRole),
          zones(move(serverZones)) {}
};


// ============================================================================
// 6. SIMULATED DNS NETWORK
// ============================================================================

class SimulatedDNSNetwork {
private:
    unordered_map<string, DNSZone> authoritativeZones;
    unordered_map<string, string> serverToZone;

public:
    SimulatedDNSNetwork() {
        DNSZone zone("example.com.");

        zone.addRecord(
            DNSRecord(
                "example.com.",
                "soa",
                "ns1.example.com. hostmaster.example.com. "
                "2026092701 3600 600 604800 300",
                3600
            )
        );

        zone.addRecord(
            DNSRecord(
                "example.com.",
                "ns",
                "ns1.example.com.",
                86400
            )
        );

        zone.addRecord(
            DNSRecord(
                "example.com.",
                "ns",
                "ns2.example.com.",
                86400
            )
        );

        zone.addRecord(
            DNSRecord(
                "example.com.",
                "a",
                "93.184.216.34",
                300
            )
        );

        zone.addRecord(
            DNSRecord(
                "example.com.",
                "aaaa",
                "2606:2800:220:1:248:1893:25c8:1946",
                300
            )
        );

        zone.addRecord(
            DNSRecord(
                "www.example.com.",
                "cname",
                "example.com.",
                600
            )
        );

        zone.addRecord(
            DNSRecord(
                "mail.example.com.",
                "a",
                "192.0.2.25",
                300
            )
        );

        zone.addRecord(
            DNSRecord(
                "example.com.",
                "mx",
                "mail.example.com.",
                3600,
                10
            )
        );

        zone.addRecord(
            DNSRecord(
                "example.com.",
                "txt",
                "v=spf1 -all",
                3600
            )
        );

        zone.addRecord(
            DNSRecord(
                "api.example.com.",
                "a",
                "192.0.2.50",
                30
            )
        );

        authoritativeZones.emplace(
            "example.com.",
            move(zone)
        );

        serverToZone["ns1.example.com."] =
            "example.com.";

        serverToZone["ns2.example.com."] =
            "example.com.";
    }

    DNSAnswer rootQuery(
        const string& name
    ) const {
        DNSAnswer answer{
            normalizeName(name),
            "ns"
        };

        const string normalizedName =
            normalizeName(name);

        const auto dotPosition =
            normalizedName.find_last_of(
                '.',
                normalizedName.size() - 2
            );

        if (dotPosition == string::npos) {
            answer.negative = true;
            answer.authoritative = true;
            return answer;
        }

        const string tld =
            normalizedName.substr(
                dotPosition + 1
            );

        if (tld == "com.") {
            answer.referralZone = "com.";
            answer.referralServers = {
                "com-tld-1."
            };

            return answer;
        }

        answer.negative = true;
        answer.authoritative = true;

        return answer;
    }

    DNSAnswer tldQuery(
        const string& name
    ) const {
        DNSAnswer answer{
            normalizeName(name),
            "ns"
        };

        if (isSubdomain(
                name,
                "example.com."
            )) {

            answer.referralZone =
                "example.com.";

            answer.referralServers = {
                "ns1.example.com.",
                "ns2.example.com."
            };

            return answer;
        }

        answer.negative = true;
        answer.authoritative = true;

        return answer;
    }

    DNSAnswer authoritativeQuery(
        const string& server,
        const string& name,
        const string& type
    ) const {
        DNSAnswer answer{
            normalizeName(name),
            toLower(type)
        };

        const string normalizedServer =
            normalizeName(server);

        auto serverIterator =
            serverToZone.find(normalizedServer);

        if (serverIterator ==
            serverToZone.end()) {

            answer.negative = true;
            return answer;
        }

        const auto zoneIterator =
            authoritativeZones.find(
                serverIterator->second
            );

        if (zoneIterator ==
            authoritativeZones.end()) {

            answer.negative = true;
            return answer;
        }

        answer.records =
            zoneIterator->second.query(
                name,
                type
            );

        answer.authoritative = true;

        if (answer.records.empty()) {
            answer.negative = true;
        }

        return answer;
    }
};


// ============================================================================
// 7. TTL CACHE
// ============================================================================

using Clock = chrono::steady_clock;
using TimePoint = Clock::time_point;

struct CacheEntry {
    vector<DNSRecord> records;
    TimePoint expiresAt;
    bool negative;

    bool expired(
        TimePoint now
    ) const {
        return now >= expiresAt;
    }

    long remainingSeconds(
        TimePoint now
    ) const {
        if (expired(now)) {
            return 0;
        }

        return chrono::duration_cast<
            chrono::seconds
        >(expiresAt - now).count();
    }
};

class DNSCache {
private:
    map<pair<string, string>, CacheEntry> entries;

public:
    optional<CacheEntry> get(
        const string& name,
        const string& type,
        TimePoint now
    ) {
        const auto key = make_pair(
            normalizeName(name),
            toLower(type)
        );

        auto iterator = entries.find(key);

        if (iterator == entries.end()) {
            return nullopt;
        }

        if (iterator->second.expired(now)) {
            entries.erase(iterator);
            return nullopt;
        }

        return iterator->second;
    }

    void put(
        const string& name,
        const string& type,
        const vector<DNSRecord>& records,
        TimePoint now,
        bool negative = false,
        optional<int> ttlOverride = nullopt
    ) {
        int ttl = 30;

        if (ttlOverride.has_value()) {
            ttl = max(0, *ttlOverride);
        } else if (!records.empty()) {
            ttl = records.front().ttl;

            for (const auto& record : records) {
                ttl = min(ttl, record.ttl);
            }
        }

        entries[
            {
                normalizeName(name),
                toLower(type)
            }
        ] = CacheEntry{
            records,
            now + chrono::seconds(ttl),
            negative
        };
    }

    size_t size() const {
        return entries.size();
    }

    size_t removeExpired(
        TimePoint now
    ) {
        size_t removed = 0;

        for (auto iterator = entries.begin();
             iterator != entries.end();) {

            if (iterator->second.expired(now)) {
                iterator = entries.erase(iterator);
                ++removed;
            } else {
                ++iterator;
            }
        }

        return removed;
    }

    void clear() {
        entries.clear();
    }
};


// ============================================================================
// 8. RESOLUTION RESULT
// ============================================================================

struct ResolutionResult {
    string name;
    string type;
    vector<DNSRecord> records;

    bool fromCache = false;
    bool authoritative = false;
    bool negative = false;

    int queriesPerformed = 0;
};


// ============================================================================
// 9. RECURSIVE RESOLVER
// ============================================================================

class RecursiveResolver {
private:
    const SimulatedDNSNetwork& network;
    DNSCache cache;

    int negativeTtl;
    int upstreamQueries = 0;

    ResolutionResult resolveUncached(
        const string& name,
        const string& type,
        TimePoint now,
        set<string>& visited,
        size_t depth
    ) {
        if (visited.count(name) != 0) {
            throw runtime_error(
                "CNAME loop detected."
            );
        }

        if (depth >= 8) {
            throw runtime_error(
                "Maximum CNAME depth exceeded."
            );
        }

        visited.insert(name);

        ++upstreamQueries;

        cout
            << "  Recursive resolver -> root\n";

        DNSAnswer rootAnswer =
            network.rootQuery(name);

        if (!rootAnswer.hasReferral()) {
            cache.put(
                name,
                type,
                {},
                now,
                true,
                negativeTtl
            );

            return {
                name,
                type,
                {},
                false,
                rootAnswer.authoritative,
                true,
                1
            };
        }

        cout
            << "  Root -> "
            << rootAnswer.referralZone
            << "\n";

        DNSAnswer tldAnswer =
            network.tldQuery(name);

        if (!tldAnswer.hasReferral()) {
            cache.put(
                name,
                type,
                {},
                now,
                true,
                negativeTtl
            );

            return {
                name,
                type,
                {},
                false,
                tldAnswer.authoritative,
                true,
                1
            };
        }

        cout
            << "  TLD -> "
            << tldAnswer.referralZone
            << "\n";

        const string authoritativeServer =
            tldAnswer.referralServers.front();

        DNSAnswer answer =
            network.authoritativeQuery(
                authoritativeServer,
                name,
                type
            );

        cout
            << "  Authoritative -> "
            << answer.records.size()
            << " record(s)\n";

        if (!answer.records.empty()) {
            cache.put(
                name,
                type,
                answer.records,
                now
            );

            return {
                name,
                type,
                answer.records,
                false,
                answer.authoritative,
                false,
                1
            };
        }

        /*
         * A query for an alias normally requires following the CNAME
         * before obtaining the requested address record.
         */
        if (type != "cname") {
            DNSAnswer cnameAnswer =
                network.authoritativeQuery(
                    authoritativeServer,
                    name,
                    "cname"
                );

            if (!cnameAnswer.records.empty()) {
                cache.put(
                    name,
                    "cname",
                    cnameAnswer.records,
                    now
                );

                const string target =
                    normalizeName(
                        cnameAnswer.records.front().value
                    );

                ResolutionResult targetResult =
                    resolveUncached(
                        target,
                        type,
                        now,
                        visited,
                        depth + 1
                    );

                return {
                    name,
                    type,
                    targetResult.records,
                    false,
                    targetResult.authoritative,
                    false,
                    1 + targetResult.queriesPerformed
                };
            }
        }

        cache.put(
            name,
            type,
            {},
            now,
            true,
            negativeTtl
        );

        return {
            name,
            type,
            {},
            false,
            answer.authoritative,
            true,
            1
        };
    }

public:
    explicit RecursiveResolver(
        const SimulatedDNSNetwork& dnsNetwork,
        int negativeCacheTtl = 30
    )
        : network(dnsNetwork),
          negativeTtl(negativeCacheTtl) {}

    ResolutionResult resolve(
        const string& name,
        const string& type,
        TimePoint now = Clock::now()
    ) {
        const string normalizedName =
            normalizeName(name);

        const string normalizedType =
            toLower(type);

        auto cached =
            cache.get(
                normalizedName,
                normalizedType,
                now
            );

        if (cached.has_value()) {
            return {
                normalizedName,
                normalizedType,
                cached->records,
                true,
                !cached->negative,
                cached->negative,
                0
            };
        }

        set<string> visited;

        return resolveUncached(
            normalizedName,
            normalizedType,
            now,
            visited,
            0
        );
    }

    const DNSCache& getCache() const {
        return cache;
    }

    int getUpstreamQueries() const {
        return upstreamQueries;
    }
};


// ============================================================================
// 10. STATISTICS
// ============================================================================

class ResolverStatistics {
private:
    long totalRequests = 0;
    long cacheHits = 0;
    long cacheMisses = 0;
    long negativeAnswers = 0;

public:
    void observe(
        const ResolutionResult& result
    ) {
        ++totalRequests;

        if (result.fromCache) {
            ++cacheHits;
        } else {
            ++cacheMisses;
        }

        if (result.negative) {
            ++negativeAnswers;
        }
    }

    double cacheHitRatio() const {
        if (totalRequests == 0) {
            return 0.0;
        }

        return static_cast<double>(cacheHits) /
               static_cast<double>(totalRequests);
    }

    void print() const {
        cout
            << "Total requests: "
            << totalRequests
            << "\n";

        cout
            << "Cache hits: "
            << cacheHits
            << "\n";

        cout
            << "Cache misses: "
            << cacheMisses
            << "\n";

        cout
            << "Negative answers: "
            << negativeAnswers
            << "\n";

        cout
            << fixed
            << setprecision(3)
            << "Cache hit ratio: "
            << cacheHitRatio()
            << "\n";
    }
};


// ============================================================================
// 11. RECORD DISPLAY
// ============================================================================

void printRecords(
    const vector<DNSRecord>& records
) {
    if (records.empty()) {
        cout << "  No records.\n";
        return;
    }

    for (const auto& record : records) {
        cout
            << "  "
            << record.toString()
            << "\n";
    }
}


// ============================================================================
// 12. BEGINNER CONCEPTS
// ============================================================================

void demonstrateBasics() {
    section("1. DNS FUNDAMENTALS");

    cout << R"(
DNS is a hierarchical distributed naming system.

A simple name:

    www.example.com.

Its labels are:

    www
    example
    com

The final dot represents the DNS root.

Hierarchy:

    .
    |
    +-- com
        |
        +-- example
            |
            +-- www

DNS is not limited to IP addresses. It also stores mail routing,
name-server delegation, aliases, policies, service locations, and
administrative information.

Important roles:

    Root server
        Points toward TLD infrastructure.

    TLD server
        Points toward delegated domain authority.

    Authoritative server
        Publishes authoritative zone data.

    Recursive resolver
        Obtains answers for clients and normally maintains a cache.
)" << "\n";

    const vector<string> names = {
        "Example.COM",
        "www.example.com.",
        "mail.example.com",
        "-bad.example.com",
        ""
    };

    for (const auto& name : names) {
        cout
            << setw(30)
            << left
            << name
            << " valid="
            << boolalpha
            << validateDnsName(name)
            << "\n";
    }
}


// ============================================================================
// 13. ZONE AND RECORD CASE STUDY
// ============================================================================

void demonstrateZone(
    const SimulatedDNSNetwork& network
) {
    section("2. AUTHORITATIVE ZONE AND RECORDS");

    /*
     * The network intentionally exposes its authoritative behavior through
     * DNS queries rather than exposing internal storage. This is similar to
     * separating an application's interface from its implementation.
     */

    const vector<pair<string, string>> queries = {
        {"example.com.", "a"},
        {"example.com.", "aaaa"},
        {"www.example.com.", "cname"},
        {"example.com.", "mx"},
        {"example.com.", "ns"},
        {"example.com.", "txt"},
        {"example.com.", "soa"}
    };

    for (const auto& [name, type] : queries) {
        DNSAnswer answer =
            network.authoritativeQuery(
                "ns1.example.com.",
                name,
                type
            );

        cout
            << "\n"
            << name
            << " "
            << type
            << "\n";

        printRecords(answer.records);
    }
}


// ============================================================================
// 14. ITERATIVE VS RECURSIVE
// ============================================================================

void explainResolutionModels() {
    section("3. ITERATIVE VS RECURSIVE RESOLUTION");

    cout << R"(
Iterative resolution:

    Requester -> Root
    Root      -> TLD referral
    Requester -> TLD
    TLD       -> Domain referral
    Requester -> Authoritative
    Authoritative -> Answer

The requester handles the referrals.

Recursive resolution:

    Client -> Recursive Resolver
                    |
                    +-> Root
                    +-> TLD
                    +-> Authoritative
                    |
                    +-> Cache
                    |
                    v
                  Client

The client normally asks one recursive resolver for the final answer.

Caching is important because it can turn a multi-stage cold lookup into a
single resolver interaction for subsequent clients.
)" << "\n";
}


// ============================================================================
// 15. CACHING CASE STUDY
// ============================================================================

void demonstrateCaching(
    const SimulatedDNSNetwork& network
) {
    section("4. TTL CACHING");

    RecursiveResolver resolver(
        network,
        30
    );

    const TimePoint base =
        Clock::now();

    cout << "First lookup:\n";

    ResolutionResult first =
        resolver.resolve(
            "example.com.",
            "a",
            base
        );

    printRecords(first.records);

    cout
        << "From cache: "
        << boolalpha
        << first.fromCache
        << "\n";

    cout << "\nSecond lookup before TTL expiration:\n";

    ResolutionResult second =
        resolver.resolve(
            "example.com.",
            "a",
            base + chrono::seconds(10)
        );

    printRecords(second.records);

    cout
        << "From cache: "
        << boolalpha
        << second.fromCache
        << "\n";

    auto cacheEntry =
        resolver.getCache().get(
            "example.com.",
            "a",
            base + chrono::seconds(10)
        );

    if (cacheEntry.has_value()) {
        cout
            << "Remaining TTL: "
            << cacheEntry->remainingSeconds(
                base + chrono::seconds(10)
            )
            << " seconds\n";
    }

    cout << "\nLookup after 300-second TTL:\n";

    ResolutionResult third =
        resolver.resolve(
            "example.com.",
            "a",
            base + chrono::seconds(301)
        );

    printRecords(third.records);

    cout
        << "From cache: "
        << boolalpha
        << third.fromCache
        << "\n";

    cout << R"(
TTL trade-off:

Short TTL:
    + Changes become visible sooner.
    - More DNS queries.

Long TTL:
    + Better cache efficiency.
    + Lower repeated lookup traffic.
    - Cached data can remain in use longer.

TTL is therefore both a performance and operational-freshness decision.
)" << "\n";
}


// ============================================================================
// 16. CNAME CASE
// ============================================================================

void demonstrateCname(
    const SimulatedDNSNetwork& network
) {
    section("5. CNAME PROCESSING");

    RecursiveResolver resolver(network);

    ResolutionResult result =
        resolver.resolve(
            "www.example.com.",
            "a"
        );

    cout
        << "Requested: www.example.com. A\n";

    cout
        << "Final address records:\n";

    printRecords(result.records);

    cout << R"(
The authoritative zone contains:

    www.example.com. CNAME example.com.

and:

    example.com. A 93.184.216.34

A recursive resolver may therefore need to:

    1. Obtain the CNAME.
    2. Follow the target name.
    3. Obtain the requested A record.
    4. Cache appropriate information.

CNAME loops and excessively long chains are failure conditions.
)" << "\n";
}


// ============================================================================
// 17. NEGATIVE CACHING
// ============================================================================

void demonstrateNegativeCaching(
    const SimulatedDNSNetwork& network
) {
    section("6. NEGATIVE CACHING");

    RecursiveResolver resolver(
        network,
        30
    );

    const TimePoint base =
        Clock::now();

    const string missing =
        "missing.example.com.";

    ResolutionResult first =
        resolver.resolve(
            missing,
            "a",
            base
        );

    cout
        << "First result: negative="
        << boolalpha
        << first.negative
        << ", cache="
        << first.fromCache
        << "\n";

    ResolutionResult second =
        resolver.resolve(
            missing,
            "a",
            base + chrono::seconds(10)
        );

    cout
        << "Second result: negative="
        << boolalpha
        << second.negative
        << ", cache="
        << second.fromCache
        << "\n";

    ResolutionResult third =
        resolver.resolve(
            missing,
            "a",
            base + chrono::seconds(31)
        );

    cout
        << "After negative TTL: negative="
        << boolalpha
        << third.negative
        << ", cache="
        << third.fromCache
        << "\n";

    cout << R"(
Negative caching reduces repeated queries for unavailable information.

Real DNS distinguishes important conditions such as:

    NXDOMAIN
        The queried name does not exist.

    NODATA
        The name exists, but the requested record type does not exist.

A production resolver must preserve these distinctions correctly.
)" << "\n";
}


// ============================================================================
// 18. ERROR AND EDGE CASES
// ============================================================================

void demonstrateEdgeCases(
    const SimulatedDNSNetwork& network
) {
    section("7. EDGE CASES AND VALIDATION");

    const vector<string> names = {
        "EXAMPLE.COM",
        "example.com.",
        "-invalid.example.com",
        "invalid-.example.com",
        "",
        "valid-name.example.com"
    };

    for (const auto& name : names) {
        cout
            << setw(32)
            << left
            << name
            << " -> "
            << boolalpha
            << validateDnsName(name)
            << "\n";
    }

    cout << "\nUnsupported TLD example:\n";

    DNSAnswer answer =
        network.rootQuery(
            "example.invalid."
        );

    cout
        << "Negative="
        << boolalpha
        << answer.negative
        << "\n";

    cout << R"(
Important real-world DNS failures include:

    NXDOMAIN
        Name does not exist.

    NODATA
        Name exists, requested type does not.

    SERVFAIL
        Resolver could not complete the query successfully.

    REFUSED
        Server refuses the request according to policy.

    Timeout
        No usable response arrived within the relevant interval.

These conditions have different meanings and should not be collapsed into
one generic "DNS is broken" category.
)" << "\n";
}


// ============================================================================
// 19. DNSSEC MODEL
// ============================================================================

struct DNSSECRecordSet {
    string name;
    string type;
    vector<DNSRecord> records;
    string signature;
};

void demonstrateDNSSEC(
    const SimulatedDNSNetwork& network
) {
    section("8. DNSSEC CONCEPTUAL MODEL");

    DNSAnswer answer =
        network.authoritativeQuery(
            "ns1.example.com.",
            "example.com.",
            "a"
        );

    DNSSECRecordSet signedSet{
        "example.com.",
        "a",
        answer.records,
        "simulated-RRSIG-signature"
    };

    cout
        << "Signed record set:\n"
        << "  Name: "
        << signedSet.name
        << "\n"
        << "  Type: "
        << signedSet.type
        << "\n"
        << "  Signature: "
        << signedSet.signature
        << "\n";

    cout << R"(
DNSSEC concepts:

    DNSKEY
        Public key material.

    RRSIG
        Signature over DNS record data.

    DS
        Parent-to-child trust relationship.

    NSEC/NSEC3
        Authenticated denial mechanisms.

DNSSEC protects DNS data integrity and authenticity through signatures.
It does not encrypt ordinary DNS queries.

Transport privacy is a separate concern addressed by mechanisms such as
DNS over TLS and DNS over HTTPS.
)" << "\n";
}


// ============================================================================
// 20. SECURITY CASE STUDY
// ============================================================================

void explainSecurity() {
    section("9. DNS SECURITY CONSIDERATIONS");

    cout << R"(
Cache poisoning:
    An attacker attempts to place forged information into a resolver cache.

Spoofing:
    A forged DNS response is presented as legitimate.

Open recursion:
    An unrestricted recursive resolver can be abused in reflection or
    amplification attacks.

DNS tunneling:
    DNS names and responses can be abused as a data transport channel.

Dangling records:
    Stale DNS records may point to resources that have been deleted.

DNS management compromise:
    Unauthorized changes at a registrar or DNS provider can redirect
    traffic.

Operational protections include:

    - Strong authentication.
    - Least-privilege administration.
    - DNSSEC where appropriate.
    - Recursive access controls.
    - DDoS protection.
    - DNS change monitoring.
    - Stale-record cleanup.
    - Careful delegation management.
    - Validation and testing of production changes.
)" << "\n";
}


// ============================================================================
// 21. PERFORMANCE ANALYSIS
// ============================================================================

void explainPerformance() {
    section("10. PERFORMANCE AND COMPLEXITY");

    cout << R"(
Cold resolution:

    Client
      |
      v
    Recursive Resolver
      |
      v
    Root
      |
      v
    TLD
      |
      v
    Authoritative Server

Cache hit:

    Client
      |
      v
    Recursive Resolver
      |
      v
    Cached Answer

This implementation uses std::map for record sets and cache entries.

Average map operations:
    Lookup     O(log n)
    Insert     O(log n)
    Delete     O(log n)

A hash-based unordered_map can provide average O(1) lookup and insertion,
though worst-case behavior and memory characteristics differ.

Real DNS performance is dominated by network latency, packet loss,
server load, delegation depth, DNSSEC validation, transport behavior,
response size, and cache hit ratio.

CNAME chains increase resolution work.

A cache hit ratio can be calculated as:

    cache hits / total client queries

Higher cache efficiency generally reduces upstream traffic, but TTL values
must still match operational freshness requirements.
)" << "\n";
}


// ============================================================================
// 22. RECORD COMPARISON
// ============================================================================

void recordComparison() {
    section("11. DNS RECORD COMPARISON");

    struct RecordDescription {
        string type;
        string purpose;
        string target;
    };

    const vector<RecordDescription> records = {
        {"A", "IPv4 address", "IPv4 address"},
        {"AAAA", "IPv6 address", "IPv6 address"},
        {"CNAME", "Alias", "DNS name"},
        {"MX", "Mail routing", "Mail server name"},
        {"NS", "Zone authority", "Name server"},
        {"TXT", "Text/policy information", "Text"},
        {"SOA", "Zone administration", "Administrative data"},
        {"PTR", "Reverse DNS", "DNS name"},
        {"SRV", "Service discovery", "Service target and port"},
        {"CAA", "Certificate policy", "CA authorization data"}
    };

    cout
        << left
        << setw(10) << "Type"
        << setw(25) << "Purpose"
        << "Target\n";

    cout << string(65, '-') << "\n";

    for (const auto& record : records) {
        cout
            << left
            << setw(10) << record.type
            << setw(25) << record.purpose
            << record.target
            << "\n";
    }
}


// ============================================================================
// 23. REALISTIC INDUSTRY SCENARIO
// ============================================================================

void industryCaseStudy(
    const SimulatedDNSNetwork& network
) {
    section("12. INDUSTRY-STYLE END-TO-END CASE");

    cout << R"(
Scenario:

A customer accesses:

    https://www.example.com/

The application needs a destination address.

Architecture:

    Web Application
          |
          v
    Client OS / Network Stack
          |
          v
    Recursive DNS Resolver
          |
          +--------------------+
          |                    |
       Cache hit             Cache miss
          |                    |
          v                    v
       Answer                Root
                               |
                               v
                              TLD
                               |
                               v
                        Authoritative
                               |
                               v
                             Records
                               |
                               v
                         Cache + Answer
                               |
                               v
                            Client

The simulated infrastructure contains:

    example.com. A
    example.com. AAAA
    www.example.com. CNAME
    mail.example.com. A
    example.com. MX
    example.com. NS
    example.com. SOA
    example.com. TXT

This illustrates why DNS is more than a simple "domain to IP" database.
)" << "\n";

    RecursiveResolver resolver(network);

    const TimePoint now =
        Clock::now();

    const vector<pair<string, string>> requests = {
        {"www.example.com.", "a"},
        {"www.example.com.", "a"},
        {"example.com.", "aaaa"},
        {"mail.example.com.", "a"},
        {"api.example.com.", "a"},
        {"api.example.com.", "a"}
    };

    ResolverStatistics statistics;

    for (const auto& [name, type] : requests) {
        cout
            << "\nApplication query: "
            << name
            << " "
            << type
            << "\n";

        ResolutionResult result =
            resolver.resolve(
                name,
                type,
                now
            );

        statistics.observe(result);

        cout
            << "Cache hit: "
            << boolalpha
            << result.fromCache
            << "\n";

        cout
            << "Negative: "
            << boolalpha
            << result.negative
            << "\n";

        cout
            << "Records:\n";

        printRecords(result.records);
    }

    cout << "\nResolver statistics:\n";
    statistics.print();

    cout
        << "\nCache entries: "
        << resolver.getCache().size()
        << "\n";

    cout
        << "Upstream operations: "
        << resolver.getUpstreamQueries()
        << "\n";
}


// ============================================================================
// 24. DESIGN CHECKLIST
// ============================================================================

void printDesignChecklist() {
    section("13. DNS PRODUCTION DESIGN CHECKLIST");

    const vector<string> checklist = {
        "Use redundant authoritative servers.",
        "Maintain consistent NS records.",
        "Define clear DNS zone boundaries.",
        "Select TTLs according to freshness and traffic requirements.",
        "Monitor authoritative DNS changes.",
        "Protect DNS provider and registrar accounts.",
        "Restrict recursive DNS service to intended clients.",
        "Remove stale DNS records.",
        "Avoid unnecessarily long CNAME chains.",
        "Test positive and negative DNS responses.",
        "Monitor DNSSEC validation where deployed.",
        "Prepare for DDoS and traffic spikes.",
        "Document dependencies between DNS and applications.",
        "Validate changes before production rollout."
    };

    for (size_t index = 0;
         index < checklist.size();
         ++index) {

        cout
            << setw(2)
            << index + 1
            << ". "
            << checklist[index]
            << "\n";
    }
}


// ============================================================================
// 25. MAIN
// ============================================================================

int main() {
    try {
        cout << R"(
##############################################################################
#                                                                            #
# DNS CASE STUDY                                                             #
# Hierarchy | Recursive Resolution | Authority | Records | Caching          #
#                                                                            #
##############################################################################
)";

        demonstrateBasics();

        SimulatedDNSNetwork network;

        demonstrateZone(network);
        explainResolutionModels();
        demonstrateCaching(network);
        demonstrateCname(network);
        demonstrateNegativeCaching(network);
        demonstrateEdgeCases(network);
        demonstrateDNSSEC(network);
        explainSecurity();
        explainPerformance();
        recordComparison();
        industryCaseStudy(network);
        printDesignChecklist();

        section("14. KEY RELATIONSHIPS");

        cout << R"(
DNS hierarchy:
    Organizes the namespace from root through TLDs and delegated zones.

Delegation:
    Assigns responsibility for a portion of the namespace.

Authoritative server:
    Publishes authoritative records for its zone.

Recursive resolver:
    Performs resolution for clients and commonly maintains a cache.

Resource records:
    Carry addresses, aliases, mail routing, delegation, policies, and
    other DNS information.

TTL:
    Defines the normal lifetime of cached information.

Caching:
    Reduces repeated upstream queries and latency.

CNAME:
    Maps one DNS name to another DNS name and may require another lookup.

DNSSEC:
    Adds cryptographic authentication and integrity to DNS data.
)";

        section("15. PROGRAM COMPLETED");

        cout
            << "The complete DNS case study executed successfully.\n";

        return 0;
    } catch (const exception& error) {
        cerr
            << "Fatal error: "
            << error.what()
            << "\n";

        return 1;
    }
}
