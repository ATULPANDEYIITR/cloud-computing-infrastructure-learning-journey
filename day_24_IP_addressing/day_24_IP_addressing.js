/*
 * IP Addressing: IPv4, IPv6, Public IP, Private IP, Reserved Addresses,
 * and IP Allocation
 *
 * Self-contained JavaScript study program.
 *
 * The implementation deliberately avoids external npm packages.
 */

// =============================================================================
// 1. BASIC IP ADDRESS REPRESENTATION
// =============================================================================

function printTitle(title) {
    console.log("\n" + "=".repeat(80));
    console.log(title);
    console.log("=".repeat(80));
}

function printSubtitle(title) {
    console.log("\n" + "-".repeat(60));
    console.log(title);
    console.log("-".repeat(60));
}

function ipv4ToInteger(address) {
    const octets = address.split(".");

    if (
        octets.length !== 4 ||
        octets.some(
            octet =>
                !/^\d+$/.test(octet) ||
                Number(octet) < 0 ||
                Number(octet) > 255
        )
    ) {
        throw new Error(`Invalid IPv4 address: ${address}`);
    }

    return (
        (Number(octets[0]) * 2 ** 24) +
        (Number(octets[1]) * 2 ** 16) +
        (Number(octets[2]) * 2 ** 8) +
        Number(octets[3])
    );
}

function integerToIpv4(value) {
    if (!Number.isInteger(value) || value < 0 || value > 0xffffffff) {
        throw new Error("IPv4 integer must be between 0 and 2^32 - 1.");
    }

    return [
        Math.floor(value / 2 ** 24),
        Math.floor((value % 2 ** 24) / 2 ** 16),
        Math.floor((value % 2 ** 16) / 2 ** 8),
        value % 2 ** 8
    ].join(".");
}

function ipv4ToBinary(address) {
    return address
        .split(".")
        .map(octet => Number(octet).toString(2).padStart(8, "0"))
        .join("");
}

function binaryToIpv4(binary) {
    if (!/^[01]{32}$/.test(binary)) {
        throw new Error("Binary IPv4 representation must contain 32 bits.");
    }

    const octets = [];

    for (let index = 0; index < 32; index += 8) {
        octets.push(parseInt(binary.slice(index, index + 8), 2));
    }

    return octets.join(".");
}

// =============================================================================
// 2. CIDR AND SUBNET MASK OPERATIONS
// =============================================================================

function ipv4MaskFromPrefix(prefixLength) {
    if (!Number.isInteger(prefixLength) || prefixLength < 0 || prefixLength > 32) {
        throw new Error("IPv4 prefix length must be between 0 and 32.");
    }

    if (prefixLength === 0) {
        return "0.0.0.0";
    }

    const mask = (0xffffffff << (32 - prefixLength)) >>> 0;
    return integerToIpv4(mask);
}

function ipv4NetworkAddress(address, prefixLength) {
    const ip = ipv4ToInteger(address);
    const mask =
        prefixLength === 0
            ? 0
            : (0xffffffff << (32 - prefixLength)) >>> 0;

    return integerToIpv4((ip & mask) >>> 0);
}

function ipv4BroadcastAddress(address, prefixLength) {
    const network = ipv4ToInteger(ipv4NetworkAddress(address, prefixLength));
    const hostBits = 32 - prefixLength;
    const blockSize = 2 ** hostBits;

    return integerToIpv4(network + blockSize - 1);
}

function ipv4AddressCount(prefixLength) {
    if (prefixLength < 0 || prefixLength > 32) {
        throw new Error("Invalid prefix length.");
    }

    return 2 ** (32 - prefixLength);
}

function parseIpv4Cidr(cidr) {
    const parts = cidr.split("/");

    if (parts.length !== 2) {
        throw new Error(`Invalid CIDR: ${cidr}`);
    }

    const address = parts[0];
    const prefix = Number(parts[1]);

    if (!Number.isInteger(prefix) || prefix < 0 || prefix > 32) {
        throw new Error(`Invalid IPv4 prefix: ${parts[1]}`);
    }

    ipv4ToInteger(address);

    return {
        address,
        prefix,
        network: ipv4NetworkAddress(address, prefix),
        broadcast: ipv4BroadcastAddress(address, prefix),
        mask: ipv4MaskFromPrefix(prefix),
        count: ipv4AddressCount(prefix)
    };
}

// =============================================================================
// 3. IPv4 SPECIAL RANGES
// =============================================================================

const ipv4SpecialRanges = [
    {
        name: "Private RFC 1918",
        network: "10.0.0.0",
        prefix: 8
    },
    {
        name: "Private RFC 1918",
        network: "172.16.0.0",
        prefix: 12
    },
    {
        name: "Private RFC 1918",
        network: "192.168.0.0",
        prefix: 16
    },
    {
        name: "Shared Address Space",
        network: "100.64.0.0",
        prefix: 10
    },
    {
        name: "Loopback",
        network: "127.0.0.0",
        prefix: 8
    },
    {
        name: "Link Local",
        network: "169.254.0.0",
        prefix: 16
    },
    {
        name: "Documentation",
        network: "192.0.2.0",
        prefix: 24
    },
    {
        name: "Documentation",
        network: "198.51.100.0",
        prefix: 24
    },
    {
        name: "Documentation",
        network: "203.0.113.0",
        prefix: 24
    },
    {
        name: "Multicast",
        network: "224.0.0.0",
        prefix: 4
    }
];

function ipv4InNetwork(address, networkAddress, prefix) {
    const addressInteger = ipv4ToInteger(address);
    const networkInteger = ipv4ToInteger(networkAddress);

    const mask =
        prefix === 0
            ? 0
            : (0xffffffff << (32 - prefix)) >>> 0;

    return (addressInteger & mask) >>> 0 ===
        (networkInteger & mask) >>> 0;
}

function classifyIpv4(address) {
    const integer = ipv4ToInteger(address);

    const result = {
        address,
        version: 4,
        private: false,
        loopback: false,
        linkLocal: false,
        multicast: false,
        documentation: false,
        sharedAddressSpace: false,
        unspecified: integer === 0,
        broadcast: integer === 0xffffffff,
        globalCandidate: true
    };

    for (const range of ipv4SpecialRanges) {
        if (ipv4InNetwork(address, range.network, range.prefix)) {
            const name = range.name.toLowerCase();

            if (name.includes("private")) result.private = true;
            if (name.includes("loopback")) result.loopback = true;
            if (name.includes("link local")) result.linkLocal = true;
            if (name.includes("multicast")) result.multicast = true;
            if (name.includes("documentation")) result.documentation = true;
            if (name.includes("shared")) result.sharedAddressSpace = true;
        }
    }

    result.globalCandidate =
        !result.private &&
        !result.loopback &&
        !result.linkLocal &&
        !result.multicast &&
        !result.documentation &&
        !result.sharedAddressSpace &&
        !result.unspecified &&
        !result.broadcast;

    return result;
}

// =============================================================================
// 4. IPV6 PARSING AND REPRESENTATION
// =============================================================================

function expandIpv6(address) {
    if (address.includes("%")) {
        throw new Error("Zone identifiers are outside this educational parser.");
    }

    let input = address;

    // Support IPv4-mapped notation such as ::ffff:192.0.2.128.
    if (input.includes(".")) {
        const lastColon = input.lastIndexOf(":");

        if (lastColon === -1) {
            throw new Error("Invalid IPv6/IPv4 mixed address.");
        }

        const ipv4Part = input.slice(lastColon + 1);
        const ipv4Integer = ipv4ToInteger(ipv4Part);

        const high = ((ipv4Integer >>> 16) & 0xffff).toString(16);
        const low = (ipv4Integer & 0xffff).toString(16);

        input = input.slice(0, lastColon + 1) + high + ":" + low;
    }

    if ((input.match(/::/g) || []).length > 1) {
        throw new Error("IPv6 address cannot contain :: more than once.");
    }

    const hasCompression = input.includes("::");

    let groups;

    if (hasCompression) {
        const [left, right] = input.split("::");

        const leftGroups = left ? left.split(":") : [];
        const rightGroups = right ? right.split(":") : [];

        if (leftGroups.some(group => !/^[0-9a-fA-F]{1,4}$/.test(group))) {
            throw new Error("Invalid IPv6 group.");
        }

        if (rightGroups.some(group => !/^[0-9a-fA-F]{1,4}$/.test(group))) {
            throw new Error("Invalid IPv6 group.");
        }

        const missing = 8 - leftGroups.length - rightGroups.length;

        if (missing < 1) {
            throw new Error("IPv6 compression does not represent omitted groups.");
        }

        groups = [
            ...leftGroups,
            ...Array(missing).fill("0"),
            ...rightGroups
        ];
    } else {
        groups = input.split(":");

        if (groups.length !== 8) {
            throw new Error("An uncompressed IPv6 address must contain 8 groups.");
        }
    }

    if (groups.length !== 8) {
        throw new Error("IPv6 address must contain exactly 8 groups after expansion.");
    }

    if (groups.some(group => !/^[0-9a-fA-F]{1,4}$/.test(group))) {
        throw new Error("Invalid IPv6 hexadecimal group.");
    }

    return groups.map(group => group.padStart(4, "0").toLowerCase());
}

function compressIpv6(address) {
    const groups = expandIpv6(address);

    let bestStart = -1;
    let bestLength = 0;

    let currentStart = -1;
    let currentLength = 0;

    for (let index = 0; index <= 8; index++) {
        if (index < 8 && groups[index] === "0000") {
            if (currentStart === -1) currentStart = index;
            currentLength++;
        } else {
            if (currentLength > bestLength) {
                bestStart = currentStart;
                bestLength = currentLength;
            }

            currentStart = -1;
            currentLength = 0;
        }
    }

    // IPv6 compression must represent at least two groups.
    if (bestLength < 2) {
        bestStart = -1;
    }

    if (bestStart === -1) {
        return groups.map(group => group.replace(/^0+(?=[0-9a-f])/, "") || "0").join(":");
    }

    const left = groups
        .slice(0, bestStart)
        .map(group => group.replace(/^0+(?=[0-9a-f])/, "") || "0");

    const right = groups
        .slice(bestStart + bestLength)
        .map(group => group.replace(/^0+(?=[0-9a-f])/, "") || "0");

    return `${left.join(":")}::${right.join(":")}`;
}

function ipv6ToBigInt(address) {
    const groups = expandIpv6(address);
    let value = 0n;

    for (const group of groups) {
        value = (value << 16n) + BigInt(`0x${group}`);
    }

    return value;
}

function bigIntToIpv6(value) {
    if (value < 0n || value > (1n << 128n) - 1n) {
        throw new Error("IPv6 integer must fit into 128 bits.");
    }

    const groups = [];

    for (let index = 7; index >= 0; index--) {
        const shift = BigInt(index * 16);
        const group = Number((value >> shift) & 0xffffn);
        groups.push(group.toString(16).padStart(4, "0"));
    }

    return compressIpv6(groups.join(":"));
}

function ipv6Network(address, prefixLength) {
    if (prefixLength < 0 || prefixLength > 128) {
        throw new Error("IPv6 prefix length must be between 0 and 128.");
    }

    const value = ipv6ToBigInt(address);
    const hostBits = 128 - prefixLength;

    const mask =
        prefixLength === 0
            ? 0n
            : ((1n << BigInt(prefixLength)) - 1n) << BigInt(hostBits);

    return bigIntToIpv6(value & mask);
}

function ipv6AddressCount(prefixLength) {
    if (prefixLength < 0 || prefixLength > 128) {
        throw new Error("Invalid IPv6 prefix length.");
    }

    return 1n << BigInt(128 - prefixLength);
}

// =============================================================================
// 5. IPV6 CLASSIFICATION
// =============================================================================

function ipv6InNetwork(address, networkAddress, prefix) {
    return ipv6Network(address, prefix) === ipv6Network(networkAddress, prefix);
}

function classifyIpv6(address) {
    const compressed = compressIpv6(address);

    const result = {
        address: compressed,
        version: 6,
        loopback: compressed === "::1",
        unspecified: compressed === "::",
        linkLocal: ipv6InNetwork(compressed, "fe80::", 10),
        uniqueLocal: ipv6InNetwork(compressed, "fc00::", 7),
        multicast: ipv6InNetwork(compressed, "ff00::", 8),
        documentation: ipv6InNetwork(compressed, "2001:db8::", 32),
        globalUnicastCandidate: ipv6InNetwork(compressed, "2000::", 3)
    };

    return result;
}

// =============================================================================
// 6. GENERIC IP DETECTION
// =============================================================================

function classifyIp(address) {
    if (address.includes(":")) {
        return classifyIpv6(address);
    }

    return classifyIpv4(address);
}

// =============================================================================
// 7. IPV4 VLSM ALLOCATION
// =============================================================================

function minimumPrefixForHosts(requiredHosts) {
    if (!Number.isInteger(requiredHosts) || requiredHosts < 1) {
        throw new Error("Host requirement must be a positive integer.");
    }

    let hostBits = 0;

    while (2 ** hostBits - 2 < requiredHosts) {
        hostBits++;
    }

    return 32 - hostBits;
}

function alignInteger(value, blockSize) {
    return Math.ceil(value / blockSize) * blockSize;
}

function allocateVlsm(baseCidr, requirements) {
    const base = parseIpv4Cidr(baseCidr);

    const baseStart = ipv4ToInteger(base.network);
    const baseEnd = ipv4ToInteger(base.broadcast);

    const ordered = [...requirements].sort(
        (left, right) => right.hosts - left.hosts
    );

    let cursor = baseStart;
    const allocations = [];

    for (const requirement of ordered) {
        const prefix = minimumPrefixForHosts(requirement.hosts);
        const blockSize = 2 ** (32 - prefix);

        cursor = alignInteger(cursor, blockSize);

        const end = cursor + blockSize - 1;

        if (end > baseEnd) {
            throw new Error(
                `Insufficient space for ${requirement.name}.`
            );
        }

        allocations.push({
            name: requirement.name,
            requiredHosts: requirement.hosts,
            prefix,
            network: integerToIpv4(cursor),
            broadcast: integerToIpv4(end),
            addressCount: blockSize
        });

        cursor = end + 1;
    }

    return allocations;
}

// =============================================================================
// 8. SIMPLE IPAM
// =============================================================================

class Ipv4Ipam {
    constructor(baseCidr) {
        this.base = parseIpv4Cidr(baseCidr);
        this.allocations = [];
    }

    overlaps(networkStart, networkEnd) {
        return this.allocations.some(allocation => {
            const start = ipv4ToInteger(allocation.network);
            const end = ipv4ToInteger(allocation.broadcast);

            return networkStart <= end && networkEnd >= start;
        });
    }

    allocate(owner, prefix, purpose) {
        if (prefix < this.base.prefix) {
            throw new Error("Requested subnet is larger than the IPAM pool.");
        }

        const blockSize = 2 ** (32 - prefix);
        const baseStart = ipv4ToInteger(this.base.network);
        const baseEnd = ipv4ToInteger(this.base.broadcast);

        for (
            let start = baseStart;
            start + blockSize - 1 <= baseEnd;
            start += blockSize
        ) {
            const end = start + blockSize - 1;

            if (!this.overlaps(start, end)) {
                const allocation = {
                    owner,
                    purpose,
                    prefix,
                    network: integerToIpv4(start),
                    broadcast: integerToIpv4(end)
                };

                this.allocations.push(allocation);
                return allocation;
            }
        }

        throw new Error("No suitable free subnet exists.");
    }

    release(network) {
        const before = this.allocations.length;

        this.allocations = this.allocations.filter(
            allocation => allocation.network !== network
        );

        if (before === this.allocations.length) {
            throw new Error(`Allocation ${network} was not found.`);
        }
    }

    print() {
        for (const allocation of this.allocations) {
            console.log(
                `${allocation.owner.padEnd(15)} ` +
                `${allocation.network}/${allocation.prefix}`.padEnd(22) +
                `${allocation.purpose}`
            );
        }
    }
}

// =============================================================================
// 9. DHCP-STYLE ALLOCATION
// =============================================================================

class DhcpPool {
    constructor(networkCidr, excluded = []) {
        this.network = parseIpv4Cidr(networkCidr);
        this.excluded = new Set(excluded);
        this.leases = new Map();
    }

    offer(clientId) {
        if (this.leases.has(clientId)) {
            return this.leases.get(clientId);
        }

        const start = ipv4ToInteger(this.network.network);
        const end = ipv4ToInteger(this.network.broadcast);

        for (let value = start + 1; value < end; value++) {
            const address = integerToIpv4(value);

            if (this.excluded.has(address)) continue;

            if ([...this.leases.values()].includes(address)) continue;

            this.leases.set(clientId, address);
            return address;
        }

        throw new Error("DHCP pool exhausted.");
    }

    release(clientId) {
        this.leases.delete(clientId);
    }
}

// =============================================================================
// 10. LONGEST-PREFIX MATCH ROUTING
// =============================================================================

class RoutingTable {
    constructor() {
        this.routes = [];
    }

    addRoute(cidr, nextHop) {
        const route = parseIpv4Cidr(cidr);

        this.routes.push({
            ...route,
            nextHop
        });
    }

    lookup(destination) {
        const destinationInteger = ipv4ToInteger(destination);

        const matches = this.routes.filter(route => {
            const start = ipv4ToInteger(route.network);
            const end = ipv4ToInteger(route.broadcast);

            return destinationInteger >= start && destinationInteger <= end;
        });

        if (matches.length === 0) {
            return null;
        }

        return matches.reduce((best, current) =>
            current.prefix > best.prefix ? current : best
        );
    }
}

// =============================================================================
// 11. NAT/PAT EDUCATIONAL MODEL
// =============================================================================

class NatTable {
    constructor(publicIp, startingPort = 40000) {
        this.publicIp = publicIp;
        this.nextPort = startingPort;
        this.entries = [];
    }

    translate(privateIp, privatePort, destinationIp, destinationPort) {
        const classification = classifyIpv4(privateIp);

        if (!classification.private) {
            throw new Error(
                "This educational NAT model expects an RFC 1918 private address."
            );
        }

        const entry = {
            privateIp,
            privatePort,
            publicIp: this.publicIp,
            publicPort: this.nextPort++,
            destinationIp,
            destinationPort
        };

        this.entries.push(entry);
        return entry;
    }
}

// =============================================================================
// 12. DEMONSTRATIONS
// =============================================================================

function demonstrateBasics() {
    printTitle("1. IPv4 FUNDAMENTALS");

    const address = "192.168.10.25";

    console.log(`Address: ${address}`);
    console.log(`Integer: ${ipv4ToInteger(address)}`);
    console.log(`Binary:  ${ipv4ToBinary(address)}`);
    console.log(`Round trip: ${integerToIpv4(ipv4ToInteger(address))}`);
}

function demonstrateSubnetting() {
    printTitle("2. CIDR AND SUBNETTING");

    for (const cidr of [
        "192.168.1.25/24",
        "10.20.30.40/16",
        "172.16.10.5/20"
    ]) {
        const details = parseIpv4Cidr(cidr);

        console.log(`\n${cidr}`);
        console.log(`Network:   ${details.network}`);
        console.log(`Broadcast: ${details.broadcast}`);
        console.log(`Mask:      ${details.mask}`);
        console.log(`Addresses: ${details.count.toLocaleString()}`);
    }

    console.log("\nIPv4 prefix capacity:");
    for (const prefix of [24, 25, 26, 27, 28, 29, 30, 31, 32]) {
        console.log(
            `/${prefix} -> ${ipv4AddressCount(prefix).toLocaleString()} addresses`
        );
    }
}

function demonstrateClassification() {
    printTitle("3. IPv4 ADDRESS CLASSIFICATION");

    const addresses = [
        "0.0.0.0",
        "8.8.8.8",
        "10.1.2.3",
        "100.64.1.1",
        "127.0.0.1",
        "169.254.1.5",
        "172.16.5.5",
        "192.168.1.5",
        "192.0.2.10",
        "203.0.113.10",
        "224.0.0.1",
        "255.255.255.255"
    ];

    for (const address of addresses) {
        console.log(`\n${address}`);
        console.log(classifyIpv4(address));
    }
}

function demonstrateIpv6() {
    printTitle("4. IPv6 REPRESENTATION");

    const addresses = [
        "2001:0db8:0000:0000:0000:ff00:0042:8329",
        "2001:db8::1",
        "::1",
        "::",
        "fe80::1",
        "fc00::1",
        "fd12:3456:789a::1",
        "ff02::1",
        "::ffff:192.0.2.128"
    ];

    for (const address of addresses) {
        console.log(`\nOriginal:   ${address}`);
        console.log(`Compressed: ${compressIpv6(address)}`);
        console.log(`Exploded:   ${expandIpv6(address).join(":")}`);
        console.log(`Classification:`);
        console.log(classifyIpv6(address));
    }

    console.log("\nIPv6 network calculations:");
    console.log(
        "2001:db8:1234:abcd::1/48 ->",
        ipv6Network("2001:db8:1234:abcd::1", 48)
    );

    console.log(
        "Addresses in /64:",
        ipv6AddressCount(64).toString()
    );
}

function demonstrateVlsm() {
    printTitle("5. VLSM ALLOCATION");

    const requirements = [
        { name: "Engineering", hosts: 100 },
        { name: "Operations", hosts: 50 },
        { name: "Finance", hosts: 30 },
        { name: "Management", hosts: 10 },
        { name: "Point-to-point", hosts: 2 }
    ];

    const allocations = allocateVlsm("192.168.50.0/24", requirements);

    for (const allocation of allocations) {
        console.log(
            `${allocation.name.padEnd(15)} ` +
            `${allocation.network}/${allocation.prefix} ` +
            `broadcast=${allocation.broadcast} ` +
            `addresses=${allocation.addressCount}`
        );
    }
}

function demonstrateIpam() {
    printTitle("6. IPAM");

    const ipam = new Ipv4Ipam("10.50.0.0/16");

    ipam.allocate("Engineering", 24, "application servers");
    ipam.allocate("Finance", 26, "workstations");
    ipam.allocate("Operations", 25, "internal services");
    ipam.allocate("Security", 27, "security infrastructure");

    ipam.print();

    console.log("\nReleasing Finance allocation...");
    ipam.release("10.50.1.0");
    ipam.print();
}

function demonstrateDhcp() {
    printTitle("7. DHCP-STYLE ALLOCATION");

    const dhcp = new DhcpPool(
        "192.168.60.0/24",
        ["192.168.60.1", "192.168.60.2", "192.168.60.10"]
    );

    for (const client of [
        "laptop-A",
        "laptop-B",
        "printer-A",
        "phone-A"
    ]) {
        console.log(`${client.padEnd(12)} -> ${dhcp.offer(client)}`);
    }

    console.log(`laptop-A again -> ${dhcp.offer("laptop-A")}`);

    dhcp.release("phone-A");
    console.log(`tablet-A -> ${dhcp.offer("tablet-A")}`);
}

function demonstrateRouting() {
    printTitle("8. LONGEST-PREFIX MATCH");

    const table = new RoutingTable();

    table.addRoute("0.0.0.0/0", "Internet Gateway");
    table.addRoute("10.0.0.0/8", "Router A");
    table.addRoute("10.20.0.0/16", "Router B");
    table.addRoute("10.20.30.0/24", "Router C");
    table.addRoute("10.20.30.128/25", "Router D");

    for (const destination of [
        "8.8.8.8",
        "10.5.5.5",
        "10.20.5.5",
        "10.20.30.50",
        "10.20.30.200"
    ]) {
        const route = table.lookup(destination);

        if (route) {
            console.log(
                `${destination.padEnd(16)} -> ` +
                `${route.network}/${route.prefix} -> ${route.nextHop}`
            );
        }
    }
}

function demonstrateNat() {
    printTitle("9. NAT/PAT");

    const nat = new NatTable("203.0.113.10");

    const connections = [
        ["192.168.1.10", 51500, "93.184.216.34", 443],
        ["192.168.1.11", 51501, "142.250.72.14", 443],
        ["10.0.0.25", 51502, "198.51.100.50", 80]
    ];

    for (const connection of connections) {
        console.log(nat.translate(...connection));
    }
}

function demonstrateIpv4VsIpv6() {
    printTitle("10. IPv4 VS IPv6");

    console.log(`
IPv4
  Address size: 32 bits
  Example:      192.168.1.10
  Broadcast:    Supported
  Loopback:     127.0.0.1
  Link-local:   169.254.0.0/16
  Private:      RFC 1918 ranges

IPv6
  Address size: 128 bits
  Example:      2001:db8::10
  Broadcast:    Not used
  Loopback:     ::1
  Link-local:   fe80::/10
  Unique local: fc00::/7
  Multicast:    ff00::/8
`);
}

function demonstrateSecurity() {
    printTitle("11. SECURITY CONSIDERATIONS");

    console.log(`
An IP address is a network-layer identifier, not a complete identity.

Important security principles:

1. Private addresses should not automatically be trusted.
2. Public addresses should not automatically be considered malicious.
3. NAT is not a replacement for firewall policy.
4. IPv4 and IPv6 filtering should be designed consistently.
5. NAT logging may be necessary to correlate public traffic with internal hosts.
6. Network segmentation should be supported by explicit routing and access-control policy.
7. Documentation prefixes should not be treated as production public allocations.
8. Source addresses can be shared, dynamically assigned, or spoofed.
`);
}

// =============================================================================
// 13. EDGE CASES AND VALIDATION
// =============================================================================

function demonstrateValidation() {
    printTitle("12. VALIDATION AND EDGE CASES");

    const values = [
        "192.168.1.1",
        "192.168.1.999",
        "2001:db8::1",
        "2001:db8:::1",
        "::1",
        "",
        "localhost"
    ];

    for (const value of values) {
        try {
            console.log(`${value || "(empty)"} ->`, classifyIp(value));
        } catch (error) {
            console.log(`${value || "(empty)"} -> INVALID: ${error.message}`);
        }
    }

    console.log("\nSpecial prefix cases:");

    for (const prefix of [0, 24, 30, 31, 32]) {
        const details = parseIpv4Cidr(`192.0.2.10/${prefix}`);
        console.log(
            `/${prefix} -> network=${details.network}, ` +
            `broadcast=${details.broadcast}, ` +
            `addresses=${details.count}`
        );
    }
}

// =============================================================================
// 14. PERFORMANCE AND DATA-STRUCTURE DISCUSSION
// =============================================================================

function demonstratePerformanceConsiderations() {
    printTitle("13. PERFORMANCE CONSIDERATIONS");

    console.log(`
Small IPAM or routing tables can use arrays and linear searches.

Large systems require more specialized structures:

  - Prefix tries
  - Patricia/radix trees
  - Hardware forwarding tables
  - Indexed databases
  - Hash-based exact-match tables

Longest-prefix matching is different from exact string matching.

For example, these routes can all match 10.20.30.200:

  0.0.0.0/0
  10.0.0.0/8
  10.20.0.0/16
  10.20.30.0/24
  10.20.30.128/25

The /25 route is the most specific match.

For large-scale IPv6 systems, JavaScript BigInt is required for exact
128-bit integer arithmetic because Number cannot exactly represent every
integer in the IPv6 address space.
`);
}

// =============================================================================
// 15. SELF-TESTS
// =============================================================================

function runSelfTests() {
    printTitle("14. SELF-TESTS");

    console.assert(
        ipv4ToBinary("255.255.255.255") === "1".repeat(32),
        "IPv4 binary conversion failed."
    );

    console.assert(
        integerToIpv4(ipv4ToInteger("192.168.1.10")) === "192.168.1.10",
        "IPv4 integer round trip failed."
    );

    console.assert(
        ipv4NetworkAddress("192.168.1.25", 24) === "192.168.1.0",
        "IPv4 network calculation failed."
    );

    console.assert(
        ipv4BroadcastAddress("192.168.1.25", 24) === "192.168.1.255",
        "IPv4 broadcast calculation failed."
    );

    console.assert(
        classifyIpv4("10.1.2.3").private === true,
        "Private IPv4 classification failed."
    );

    console.assert(
        classifyIpv4("127.0.0.1").loopback === true,
        "Loopback classification failed."
    );

    console.assert(
        compressIpv6("2001:0db8:0000:0000:0000:0000:0000:0001") ===
            "2001:db8::1",
        "IPv6 compression failed."
    );

    console.assert(
        compressIpv6("::1") === "::1",
        "IPv6 loopback compression failed."
    );

    console.assert(
        ipv6Network("2001:db8:1234:abcd::1", 48) ===
            "2001:db8:1234::",
        "IPv6 network calculation failed."
    );

    const table = new RoutingTable();

    table.addRoute("0.0.0.0/0", "default");
    table.addRoute("10.0.0.0/8", "A");
    table.addRoute("10.1.0.0/16", "B");
    table.addRoute("10.1.2.0/24", "C");

    console.assert(
        table.lookup("10.1.2.50").nextHop === "C",
        "Longest-prefix matching failed."
    );

    console.assert(
        table.lookup("10.1.50.50").nextHop === "B",
        "Longest-prefix matching failed."
    );

    console.assert(
        table.lookup("10.2.50.50").nextHop === "A",
        "Longest-prefix matching failed."
    );

    console.assert(
        table.lookup("8.8.8.8").nextHop === "default",
        "Default route lookup failed."
    );

    console.log("All JavaScript self-tests passed.");
}

// =============================================================================
// 16. MAIN
// =============================================================================

function main() {
    printTitle("IP ADDRESSING COMPLETE JAVASCRIPT STUDY");

    demonstrateBasics();
    demonstrateSubnetting();
    demonstrateClassification();
    demonstrateIpv6();
    demonstrateVlsm();
    demonstrateIpam();
    demonstrateDhcp();
    demonstrateRouting();
    demonstrateNat();
    demonstrateIpv4VsIpv6();
    demonstrateSecurity();
    demonstrateValidation();
    demonstratePerformanceConsiderations();
    runSelfTests();
}

main();
