"use strict";

/*
 * DNS: Hierarchy, Recursive Resolution, Authoritative Servers,
 *     DNS Records, and Caching
 *
 * This standalone JavaScript file complements the Python study program.
 * It focuses on JavaScript data modeling, classes, Maps, validation,
 * recursive resolution, TTL caching, asynchronous behavior, and a
 * browser/application-oriented view of DNS.
 *
 * Run with:
 *     node dns-study.js
 *
 * No external npm packages are required.
 */

// ============================================================================
// 1. GENERAL UTILITIES
// ============================================================================

function section(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}

function sleep(milliseconds) {
    return new Promise(resolve => setTimeout(resolve, milliseconds));
}

function normalizeName(name) {
    if (typeof name !== "string" || name.trim() === "") {
        throw new TypeError("DNS name must be a non-empty string.");
    }

    let normalized = name.trim().toLowerCase();

    if (!normalized.endsWith(".")) {
        normalized += ".";
    }

    return normalized;
}

function validateDnsName(name) {
    try {
        const normalized = normalizeName(name);

        if (normalized === ".") {
            return true;
        }

        if (normalized.length > 253) {
            return false;
        }

        const labels = normalized.slice(0, -1).split(".");

        return labels.every(label => {
            if (label.length < 1 || label.length > 63) {
                return false;
            }

            if (label.startsWith("-") || label.endsWith("-")) {
                return false;
            }

            return /^[a-z0-9-]+$/i.test(label);
        });
    } catch {
        return false;
    }
}


// ============================================================================
// 2. BASIC DNS DATA MODEL
// ============================================================================

class DNSRecord {
    constructor({
        name,
        type,
        value,
        ttl,
        priority = null
    }) {
        this.name = normalizeName(name);
        this.type = String(type).toUpperCase();
        this.value = value;
        this.ttl = ttl;
        this.priority = priority;
    }

    toString() {
        const priorityText =
            this.priority === null
                ? ""
                : ` priority=${this.priority}`;

        return `${this.name} ${this.ttl} IN ${this.type} ${this.value}${priorityText}`;
    }
}

class DNSZone {
    constructor(origin) {
        this.origin = normalizeName(origin);
        this.records = new Map();
    }

    key(name, type) {
        return `${normalizeName(name)}|${String(type).toUpperCase()}`;
    }

    addRecord(record) {
        const key = this.key(record.name, record.type);

        if (!this.records.has(key)) {
            this.records.set(key, []);
        }

        this.records.get(key).push(record);
    }

    query(name, type) {
        return [...(this.records.get(this.key(name, type)) || [])];
    }

    hasName(name) {
        const normalized = normalizeName(name);

        for (const records of this.records.values()) {
            for (const record of records) {
                if (record.name === normalized) {
                    return true;
                }
            }
        }

        return false;
    }
}


// ============================================================================
// 3. BUILD AN AUTHORITATIVE ZONE
// ============================================================================

function buildExampleZone() {
    const zone = new DNSZone("example.com.");

    zone.addRecord(new DNSRecord({
        name: "example.com.",
        type: "SOA",
        value:
            "ns1.example.com. hostmaster.example.com. " +
            "2026092701 3600 600 604800 300",
        ttl: 3600
    }));

    zone.addRecord(new DNSRecord({
        name: "example.com.",
        type: "NS",
        value: "ns1.example.com.",
        ttl: 86400
    }));

    zone.addRecord(new DNSRecord({
        name: "example.com.",
        type: "NS",
        value: "ns2.example.com.",
        ttl: 86400
    }));

    zone.addRecord(new DNSRecord({
        name: "example.com.",
        type: "A",
        value: "93.184.216.34",
        ttl: 300
    }));

    zone.addRecord(new DNSRecord({
        name: "example.com.",
        type: "AAAA",
        value: "2606:2800:220:1:248:1893:25c8:1946",
        ttl: 300
    }));

    zone.addRecord(new DNSRecord({
        name: "www.example.com.",
        type: "CNAME",
        value: "example.com.",
        ttl: 600
    }));

    zone.addRecord(new DNSRecord({
        name: "mail.example.com.",
        type: "A",
        value: "192.0.2.25",
        ttl: 300
    }));

    zone.addRecord(new DNSRecord({
        name: "example.com.",
        type: "MX",
        value: "mail.example.com.",
        priority: 10,
        ttl: 3600
    }));

    zone.addRecord(new DNSRecord({
        name: "example.com.",
        type: "TXT",
        value: "v=spf1 -all",
        ttl: 3600
    }));

    zone.addRecord(new DNSRecord({
        name: "api.example.com.",
        type: "A",
        value: "192.0.2.50",
        ttl: 30
    }));

    return zone;
}


// ============================================================================
// 4. SERVER ROLE MODEL
// ============================================================================

const ServerRole = Object.freeze({
    ROOT: "root",
    TLD: "tld",
    AUTHORITATIVE: "authoritative",
    RECURSIVE: "recursive"
});

class DNSServer {
    constructor(name, role, zones = []) {
        this.name = normalizeName(name);
        this.role = role;
        this.zones = zones.map(normalizeName);
    }

    describe() {
        return {
            name: this.name,
            role: this.role,
            zones: [...this.zones]
        };
    }
}


// ============================================================================
// 5. SIMULATED DNS NETWORK
// ============================================================================

class SimulatedDNSNetwork {
    constructor() {
        this.rootServers = new Map();
        this.tldServers = new Map();
        this.authoritativeZones = new Map();
        this.zonesByServer = new Map();

        this.rootDelegations = new Map([
            ["com.", ["com-tld-1."]]
        ]);

        this.tldDelegations = new Map([
            [
                "example.com.",
                ["ns1.example.com.", "ns2.example.com."]
            ]
        ]);

        this.rootServers.set(
            "root-1.",
            new DNSServer("root-1.", ServerRole.ROOT, ["."])
        );

        this.tldServers.set(
            "com-tld-1.",
            new DNSServer("com-tld-1.", ServerRole.TLD, ["com."])
        );

        const exampleZone = buildExampleZone();

        this.authoritativeZones.set(
            "example.com.",
            exampleZone
        );

        this.zonesByServer.set(
            "ns1.example.com.",
            exampleZone
        );

        this.zonesByServer.set(
            "ns2.example.com.",
            exampleZone
        );
    }

    isSubdomain(name, zone) {
        const normalizedName = normalizeName(name);
        const normalizedZone = normalizeName(zone);

        if (normalizedZone === ".") {
            return true;
        }

        return (
            normalizedName === normalizedZone ||
            normalizedName.endsWith(normalizedZone)
        );
    }

    rootQuery(name) {
        const normalizedName = normalizeName(name);
        const labels = normalizedName
            .replace(/\.$/, "")
            .split(".");

        const tld = labels[labels.length - 1] + ".";

        if (!this.rootDelegations.has(tld)) {
            return {
                records: [],
                authoritative: true,
                negative: true
            };
        }

        return {
            records: [],
            authoritative: false,
            referral: {
                zone: tld,
                servers: this.rootDelegations.get(tld)
            }
        };
    }

    tldQuery(name) {
        const normalizedName = normalizeName(name);

        let bestMatch = null;

        for (const zone of this.tldDelegations.keys()) {
            if (
                this.isSubdomain(normalizedName, zone) &&
                (bestMatch === null || zone.length > bestMatch.length)
            ) {
                bestMatch = zone;
            }
        }

        if (bestMatch === null) {
            return {
                records: [],
                authoritative: true,
                negative: true
            };
        }

        return {
            records: [],
            authoritative: false,
            referral: {
                zone: bestMatch,
                servers: this.tldDelegations.get(bestMatch)
            }
        };
    }

    authoritativeQuery(serverName, name, type) {
        const normalizedServer = normalizeName(serverName);
        const normalizedName = normalizeName(name);
        const normalizedType = String(type).toUpperCase();

        const zone = this.zonesByServer.get(normalizedServer);

        if (!zone) {
            return {
                records: [],
                authoritative: false,
                negative: true
            };
        }

        const records = zone.query(
            normalizedName,
            normalizedType
        );

        if (records.length > 0) {
            return {
                records,
                authoritative: true,
                negative: false
            };
        }

        return {
            records: [],
            authoritative: true,
            negative: true
        };
    }
}


// ============================================================================
// 6. ITERATIVE RESOLUTION
// ============================================================================

function iterativeResolution(network, name, type) {
    const normalizedName = normalizeName(name);
    const normalizedType = String(type).toUpperCase();

    console.log(
        `\nIterative resolution: ${normalizedName} ${normalizedType}`
    );

    const rootAnswer = network.rootQuery(normalizedName);

    if (!rootAnswer.referral) {
        return rootAnswer;
    }

    console.log(
        `  ROOT -> ${rootAnswer.referral.zone} referral`
    );

    const tldServer = rootAnswer.referral.servers[0];

    const tldAnswer = network.tldQuery(normalizedName);

    if (!tldAnswer.referral) {
        return tldAnswer;
    }

    console.log(
        `  TLD  -> ${tldAnswer.referral.zone} referral`
    );

    const authoritativeServer =
        tldAnswer.referral.servers[0];

    const finalAnswer = network.authoritativeQuery(
        authoritativeServer,
        normalizedName,
        normalizedType
    );

    console.log(
        `  AUTH -> ${finalAnswer.records.length} record(s)`
    );

    return finalAnswer;
}


// ============================================================================
// 7. TTL CACHE
// ============================================================================

class DNSCache {
    constructor() {
        this.entries = new Map();
    }

    key(name, type) {
        return `${normalizeName(name)}|${String(type).toUpperCase()}`;
    }

    get(name, type, now = Date.now()) {
        const key = this.key(name, type);
        const entry = this.entries.get(key);

        if (!entry) {
            return null;
        }

        if (now >= entry.expiresAt) {
            this.entries.delete(key);
            return null;
        }

        return {
            ...entry,
            remainingTtl: Math.max(
                0,
                Math.floor((entry.expiresAt - now) / 1000)
            )
        };
    }

    put(
        name,
        type,
        records,
        now = Date.now(),
        negative = false,
        ttlOverride = null
    ) {
        const recordList = [...records];

        let ttl;

        if (ttlOverride !== null) {
            ttl = Math.max(0, ttlOverride);
        } else if (recordList.length > 0) {
            ttl = Math.min(
                ...recordList.map(record => record.ttl)
            );
        } else {
            ttl = 30;
        }

        this.entries.set(
            this.key(name, type),
            {
                records: recordList,
                expiresAt: now + ttl * 1000,
                negative
            }
        );
    }

    removeExpired(now = Date.now()) {
        let removed = 0;

        for (const [key, entry] of this.entries) {
            if (now >= entry.expiresAt) {
                this.entries.delete(key);
                removed++;
            }
        }

        return removed;
    }

    size() {
        return this.entries.size;
    }

    clear() {
        this.entries.clear();
    }
}


// ============================================================================
// 8. RECURSIVE RESOLVER
// ============================================================================

class RecursiveResolver {
    constructor(network, negativeTtl = 30) {
        this.network = network;
        this.cache = new DNSCache();
        this.negativeTtl = negativeTtl;
        this.upstreamQueries = 0;
    }

    resolve(
        name,
        type,
        now = Date.now(),
        maxCnameDepth = 8
    ) {
        const normalizedName = normalizeName(name);
        const normalizedType = String(type).toUpperCase();

        const cached = this.cache.get(
            normalizedName,
            normalizedType,
            now
        );

        if (cached) {
            return {
                name: normalizedName,
                type: normalizedType,
                records: cached.records,
                fromCache: true,
                authoritative: !cached.negative,
                negative: cached.negative,
                queriesPerformed: 0
            };
        }

        return this.resolveUncached(
            normalizedName,
            normalizedType,
            now,
            maxCnameDepth,
            new Set()
        );
    }

    resolveUncached(
        name,
        type,
        now,
        maxCnameDepth,
        visited
    ) {
        if (visited.has(name)) {
            throw new Error("CNAME loop detected.");
        }

        if (visited.size >= maxCnameDepth) {
            throw new Error(
                "Maximum CNAME chain depth exceeded."
            );
        }

        visited.add(name);

        this.upstreamQueries++;

        const answer = iterativeResolution(
            this.network,
            name,
            type
        );

        if (answer.records.length > 0) {
            this.cache.put(
                name,
                type,
                answer.records,
                now
            );

            return {
                name,
                type,
                records: answer.records,
                fromCache: false,
                authoritative: answer.authoritative,
                negative: false,
                queriesPerformed: 1
            };
        }

        /*
         * If the requested type is not CNAME, check whether this owner
         * name is an alias. This models the common CNAME-following path.
         */
        if (type !== "CNAME") {
            const cnameAnswer = iterativeResolution(
                this.network,
                name,
                "CNAME"
            );

            if (cnameAnswer.records.length > 0) {
                this.cache.put(
                    name,
                    "CNAME",
                    cnameAnswer.records,
                    now
                );

                const target =
                    normalizeName(cnameAnswer.records[0].value);

                const targetResult =
                    this.resolveUncached(
                        target,
                        type,
                        now,
                        maxCnameDepth,
                        visited
                    );

                return {
                    name,
                    type,
                    records: targetResult.records,
                    fromCache: false,
                    authoritative:
                        targetResult.authoritative,
                    negative: false,
                    queriesPerformed:
                        1 + targetResult.queriesPerformed
                };
            }
        }

        this.cache.put(
            name,
            type,
            [],
            now,
            true,
            this.negativeTtl
        );

        return {
            name,
            type,
            records: [],
            fromCache: false,
            authoritative: answer.authoritative,
            negative: true,
            queriesPerformed: 1
        };
    }
}


// ============================================================================
// 9. BEGINNER EXAMPLES
// ============================================================================

function beginnerExamples() {
    section("1. BEGINNER DNS EXAMPLES");

    const domain = "www.example.com.";

    console.log(`Domain: ${domain}`);

    console.log(
        "Labels:",
        domain
            .replace(/\.$/, "")
            .split(".")
    );

    console.log(
        "Normalized:",
        normalizeName("WWW.Example.COM")
    );

    console.log(
        "Valid:",
        validateDnsName("api.example.com")
    );

    console.log(
        "Invalid:",
        validateDnsName("-bad.example.com")
    );

    console.log(
        `
DNS hierarchy:

    .
    |
    +-- com
        |
        +-- example
            |
            +-- www

A recursive resolver can follow this hierarchy to find authoritative
data and can cache the result according to TTL.
`
    );
}


// ============================================================================
// 10. RECORD EXAMPLES
// ============================================================================

function recordExamples(zone) {
    section("2. DNS RECORD TYPES");

    const recordsToShow = [
        ...zone.query("example.com.", "A"),
        ...zone.query("example.com.", "AAAA"),
        ...zone.query("www.example.com.", "CNAME"),
        ...zone.query("example.com.", "MX"),
        ...zone.query("example.com.", "NS"),
        ...zone.query("example.com.", "TXT")
    ];

    for (const record of recordsToShow) {
        console.log(record.toString());
    }

    console.log(`
A      -> IPv4 address
AAAA   -> IPv6 address
CNAME  -> Alias to another DNS name
MX     -> Mail exchange
NS     -> Authoritative name server
TXT    -> Arbitrary text data used by many DNS-based policies
SOA    -> Zone administration information
PTR    -> Reverse DNS mapping
SRV    -> Service location information
CAA    -> Certificate-authority authorization
`);
}


// ============================================================================
// 11. RECURSIVE RESOLUTION AND CACHE
// ============================================================================

function cachingExample(network, resolver) {
    section("3. RECURSIVE RESOLUTION AND CACHING");

    const baseTime = 1_000_000_000;

    const first = resolver.resolve(
        "example.com.",
        "A",
        baseTime
    );

    console.log(
        "First lookup:",
        first.records.map(record => record.toString()),
        "cache:",
        first.fromCache
    );

    const second = resolver.resolve(
        "example.com.",
        "A",
        baseTime + 10_000
    );

    const cacheEntry = resolver.cache.get(
        "example.com.",
        "A",
        baseTime + 10_000
    );

    console.log(
        "Second lookup:",
        second.records.map(record => record.toString()),
        "cache:",
        second.fromCache,
        "remaining TTL:",
        cacheEntry?.remainingTtl
    );

    const third = resolver.resolve(
        "example.com.",
        "A",
        baseTime + 301_000
    );

    console.log(
        "After TTL expiration:",
        third.records.map(record => record.toString()),
        "cache:",
        third.fromCache
    );
}


// ============================================================================
// 12. CNAME CHAIN
// ============================================================================

function cnameExample(resolver) {
    section("4. CNAME RESOLUTION");

    const result = resolver.resolve(
        "www.example.com.",
        "A",
        2_000_000_000
    );

    console.log(
        "www.example.com A ->",
        result.records.map(record => record.value)
    );

    console.log(
        "CNAME cache entry ->",
        resolver.cache.get(
            "www.example.com.",
            "CNAME",
            2_000_000_000
        )?.records.map(record => record.toString())
    );
}


// ============================================================================
// 13. NEGATIVE CACHING
// ============================================================================

function negativeCachingExample(resolver) {
    section("5. NEGATIVE CACHING");

    const baseTime = 3_000_000_000;
    const name = "unknown.example.com.";

    const first = resolver.resolve(
        name,
        "A",
        baseTime
    );

    console.log(
        "First:",
        {
            records: first.records,
            negative: first.negative,
            cache: first.fromCache
        }
    );

    const second = resolver.resolve(
        name,
        "A",
        baseTime + 10_000
    );

    console.log(
        "Second:",
        {
            records: second.records,
            negative: second.negative,
            cache: second.fromCache
        }
    );

    const third = resolver.resolve(
        name,
        "A",
        baseTime + 31_000
    );

    console.log(
        "After negative TTL:",
        {
            records: third.records,
            negative: third.negative,
            cache: third.fromCache
        }
    );
}


// ============================================================================
// 14. ASYNCHRONOUS APPLICATION BEHAVIOR
// ============================================================================

async function asynchronousDnsSimulation(resolver) {
    section("6. ASYNCHRONOUS DNS APPLICATION MODEL");

    /*
     * JavaScript applications frequently use asynchronous operations.
     * Real browser DNS resolution is normally handled by the browser
     * networking stack rather than JavaScript directly.
     *
     * This function simulates an asynchronous application request to a
     * DNS service so that Promise/async/await behavior can be demonstrated.
     */

    async function lookup(name, type) {
        await sleep(20);

        return resolver.resolve(
            name,
            type,
            Date.now()
        );
    }

    try {
        const result = await lookup(
            "api.example.com.",
            "A"
        );

        console.log(
            "Asynchronous result:",
            result.records.map(record => record.value)
        );
    } catch (error) {
        console.error(
            "Asynchronous DNS failure:",
            error.message
        );
    }
}


// ============================================================================
// 15. CONCURRENT APPLICATION REQUESTS
// ============================================================================

async function concurrentLookups(resolver) {
    section("7. CONCURRENT DNS-STYLE LOOKUPS");

    /*
     * Promise.all represents independent asynchronous operations.
     * A real browser may perform DNS work concurrently as part of
     * connection establishment, though JavaScript does not control
     * the browser's internal resolver implementation.
     */

    const names = [
        "example.com.",
        "mail.example.com.",
        "api.example.com."
    ];

    const results = await Promise.all(
        names.map(async name => {
            await sleep(10);

            return {
                name,
                result: resolver.resolve(
                    name,
                    "A",
                    Date.now()
                )
            };
        })
    );

    for (const item of results) {
        console.log(
            item.name,
            "->",
            item.result.records.map(record => record.value),
            "cache:",
            item.result.fromCache
        );
    }
}


// ============================================================================
// 16. ERROR HANDLING AND VALIDATION
// ============================================================================

function errorHandlingExamples(resolver) {
    section("8. VALIDATION AND ERROR HANDLING");

    const invalidInputs = [
        "",
        "-bad.example.com",
        "bad-.example.com"
    ];

    for (const input of invalidInputs) {
        try {
            if (!validateDnsName(input)) {
                throw new Error(
                    `Invalid DNS name: ${JSON.stringify(input)}`
                );
            }

            console.log("Valid:", input);
        } catch (error) {
            console.log(
                "Validation error:",
                error.message
            );
        }
    }

    try {
        resolver.resolve(
            "example.com.",
            "A"
        );

        console.log(
            "Valid resolution request accepted."
        );
    } catch (error) {
        console.error(
            "Resolution failure:",
            error.message
        );
    }
}


// ============================================================================
// 17. DNSSEC CONCEPTUAL MODEL
// ============================================================================

class DNSSECRecordSet {
    constructor(name, type, records, signature) {
        this.name = normalizeName(name);
        this.type = type.toUpperCase();
        this.records = records;
        this.signature = signature;
    }

    describe() {
        return {
            name: this.name,
            type: this.type,
            recordCount: this.records.length,
            signature: this.signature
        };
    }
}

function dnssecExample(zone) {
    section("9. DNSSEC DATA MODEL");

    const aRecords = zone.query(
        "example.com.",
        "A"
    );

    const signedSet = new DNSSECRecordSet(
        "example.com.",
        "A",
        aRecords,
        "RRSIG(A): simulated-digital-signature"
    );

    console.log(
        signedSet.describe()
    );

    console.log(`
DNSSEC concepts:

DNSKEY -> public key information
RRSIG  -> signature covering DNS record data
DS     -> parent-to-child trust relationship
NSEC/NSEC3 -> authenticated denial mechanisms

DNSSEC authenticates DNS data. It does not make ordinary DNS traffic
confidential. Transport privacy is addressed by mechanisms such as
DNS over TLS and DNS over HTTPS.
`);
}


// ============================================================================
// 18. CACHE STATISTICS
// ============================================================================

class ResolverStatistics {
    constructor() {
        this.totalRequests = 0;
        this.cacheHits = 0;
        this.cacheMisses = 0;
        this.negativeAnswers = 0;
    }

    observe(result) {
        this.totalRequests++;

        if (result.fromCache) {
            this.cacheHits++;
        } else {
            this.cacheMisses++;
        }

        if (result.negative) {
            this.negativeAnswers++;
        }
    }

    get hitRatio() {
        if (this.totalRequests === 0) {
            return 0;
        }

        return this.cacheHits / this.totalRequests;
    }

    describe() {
        return {
            totalRequests: this.totalRequests,
            cacheHits: this.cacheHits,
            cacheMisses: this.cacheMisses,
            negativeAnswers: this.negativeAnswers,
            cacheHitRatio: Number(
                this.hitRatio.toFixed(3)
            )
        };
    }
}

function statisticsExample(resolver) {
    section("10. RESOLVER CACHE STATISTICS");

    const statistics = new ResolverStatistics();

    const queries = [
        ["example.com.", "A"],
        ["example.com.", "A"],
        ["www.example.com.", "A"],
        ["www.example.com.", "A"],
        ["api.example.com.", "A"],
        ["unknown.example.com.", "A"],
        ["unknown.example.com.", "A"]
    ];

    const now = Date.now();

    for (const [name, type] of queries) {
        const result = resolver.resolve(
            name,
            type,
            now
        );

        statistics.observe(result);
    }

    console.log(
        statistics.describe()
    );
}


// ============================================================================
// 19. SECURITY DESIGN NOTES
// ============================================================================

function securityConsiderations() {
    section("11. DNS SECURITY CONSIDERATIONS");

    console.log(`
Important DNS security areas:

1. Cache poisoning
   False data is inserted into a resolver's cache.

2. Spoofing
   An attacker attempts to make a forged response appear legitimate.

3. Open recursive resolvers
   Unrestricted recursive service can be abused in reflection/amplification
   attacks.

4. DNS tunneling
   DNS traffic can be abused to transport data in unusual ways.

5. Dangling DNS records
   Stale records can point to resources that no longer belong to the
   intended organization.

6. DNS management compromise
   Unauthorized changes to DNS provider accounts can redirect traffic.

7. DNSSEC validation failures
   Broken signatures or trust chains can prevent successful validation.

Useful controls include:

- Strong authentication for DNS management.
- Least-privilege access.
- Monitoring DNS changes.
- Restricting recursion.
- DDoS protection.
- DNSSEC where appropriate.
- Removal of stale records.
- Careful delegation management.
`);
}


// ============================================================================
// 20. PERFORMANCE MODEL
// ============================================================================

function performanceModel() {
    section("12. PERFORMANCE AND COMPLEXITY");

    console.log(`
Typical cold resolution:

    Client
      |
      v
    Recursive resolver
      |
      v
    Root
      |
      v
    TLD
      |
      v
    Authoritative server

Typical cache hit:

    Client
      |
      v
    Recursive resolver
      |
      v
    Cached answer

JavaScript Map operations are approximately O(1) average-case for lookup,
insertion, and deletion.

The network portion of DNS resolution is dominated by latency, packet
loss, server processing, delegation depth, DNSSEC work, and transport
behavior rather than local Map complexity.

CNAME chains can increase the number of resolution operations.

Cache hit ratio:

    cacheHits / totalRequests

A larger TTL can improve cache efficiency while causing stale information
to persist longer. A smaller TTL can make changes visible sooner but can
increase upstream DNS traffic.
`);
}


// ============================================================================
// 21. RECORD COMPARISON
// ============================================================================

function recordComparison() {
    section("13. IMPORTANT RECORD DISTINCTIONS");

    const comparison = [
        {
            type: "A",
            purpose: "IPv4 address",
            target: "Address",
            commonUse: "Web and application hosts"
        },
        {
            type: "AAAA",
            purpose: "IPv6 address",
            target: "Address",
            commonUse: "IPv6-enabled hosts"
        },
        {
            type: "CNAME",
            purpose: "Alias",
            target: "Another DNS name",
            commonUse: "Canonical naming and service aliases"
        },
        {
            type: "MX",
            purpose: "Mail routing",
            target: "Mail server name",
            commonUse: "Email delivery"
        },
        {
            type: "NS",
            purpose: "Zone authority",
            target: "Name server",
            commonUse: "Delegation and authoritative service"
        },
        {
            type: "TXT",
            purpose: "Text/policy data",
            target: "Text",
            commonUse: "Verification and email policies"
        }
    ];

    console.table(comparison);
}


// ============================================================================
// 22. END-TO-END CASE STUDY
// ============================================================================

function endToEndCase(resolver) {
    section("14. END-TO-END WEB REQUEST CASE");

    console.log(`
Application URL:

    https://www.example.com/

Before an application can establish a connection to the destination,
the operating system/browser networking stack may need an address for
www.example.com.

Conceptually:

    Application
        |
        v
    Local DNS configuration
        |
        v
    Recursive resolver
        |
        +---- cache hit ----------> answer
        |
        +---- cache miss
                  |
                  v
                Root
                  |
                  v
                TLD
                  |
                  v
            Authoritative server
                  |
                  v
              DNS records
                  |
                  v
            Recursive resolver
                  |
                  v
                Client
`);

    const result = resolver.resolve(
        "www.example.com.",
        "A",
        Date.now()
    );

    console.log(
        "Resolved addresses:",
        result.records.map(record => record.value)
    );

    console.log(
        "Used cache:",
        result.fromCache
    );
}


// ============================================================================
// 23. MAIN
// ============================================================================

async function main() {
    console.log(`
##############################################################################
#                                                                            #
# DNS STUDY LAB                                                             #
# Hierarchy | Recursive Resolution | Authority | Records | Caching          #
#                                                                            #
##############################################################################
`);

    beginnerExamples();

    const network = new SimulatedDNSNetwork();
    const zone = network.authoritativeZones.get(
        "example.com."
    );

    recordExamples(zone);

    const resolver = new RecursiveResolver(
        network,
        30
    );

    cachingExample(
        network,
        resolver
    );

    cnameExample(resolver);
    negativeCachingExample(resolver);

    await asynchronousDnsSimulation(
        resolver
    );

    await concurrentLookups(
        resolver
    );

    errorHandlingExamples(
        resolver
    );

    dnssecExample(zone);

    statisticsExample(
        resolver
    );

    securityConsiderations();
    performanceModel();
    recordComparison();
    endToEndCase(resolver);

    section("15. KEY DNS RELATIONSHIPS");

    console.log(`
Hierarchy
    Defines the distributed namespace.

Delegation
    Transfers authority between DNS zones.

Authoritative server
    Publishes authoritative zone information.

Recursive resolver
    Obtains answers for clients.

Iterative queries
    Allow a resolver to follow referrals through the hierarchy.

Resource records
    Carry DNS information.

TTL
    Limits how long ordinary cached data should be reused.

Caching
    Reduces latency and upstream traffic.

CNAME
    Adds an aliasing step that can require additional resolution.

DNSSEC
    Adds cryptographic authentication and integrity to DNS data.
`);

    section("16. PROGRAM COMPLETED");

    console.log(
        "Cache entries currently stored:",
        resolver.cache.size()
    );

    console.log(
        "Upstream resolution operations:",
        resolver.upstreamQueries
    );
}

main().catch(error => {
    console.error(
        "\nFatal error:",
        error.message
    );

    process.exitCode = 1;
});
