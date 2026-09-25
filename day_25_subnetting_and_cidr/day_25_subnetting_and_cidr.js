"use strict";

/*
 * SUBNETTING AND CIDR
 * ===================
 *
 * A self-contained JavaScript study program covering:
 *
 * - IPv4 addresses
 * - Binary representation
 * - Subnet masks
 * - CIDR prefixes
 * - Network and broadcast addresses
 * - Host ranges
 * - Fixed-length subnetting
 * - VLSM
 * - Network membership
 * - Range overlap
 * - Route summarization
 * - Longest-prefix matching
 * - Validation
 * - Edge cases
 * - Practical network design
 *
 * The implementation uses only standard JavaScript features and is
 * executable with Node.js.
 */

// ---------------------------------------------------------------------------
// IPv4 CONVERSION AND VALIDATION
// ---------------------------------------------------------------------------

function validateOctet(value) {
    return Number.isInteger(value) && value >= 0 && value <= 255;
}

function ipv4ToInteger(address) {
    if (typeof address !== "string") {
        throw new TypeError("IPv4 address must be a string.");
    }

    const parts = address.split(".");

    if (parts.length !== 4) {
        throw new Error(`Invalid IPv4 address: ${address}`);
    }

    const octets = parts.map((part) => {
        if (!/^\d+$/.test(part)) {
            throw new Error(`Invalid IPv4 octet: ${part}`);
        }

        const value = Number(part);

        if (!validateOctet(value)) {
            throw new Error(`IPv4 octet out of range: ${part}`);
        }

        return value;
    });

    // JavaScript bitwise operations use signed 32-bit integers.
    // >>> 0 converts the result to an unsigned 32-bit representation.
    return (
        ((octets[0] << 24) >>> 0) |
        (octets[1] << 16) |
        (octets[2] << 8) |
        octets[3]
    ) >>> 0;
}

function integerToIPv4(value) {
    if (!Number.isInteger(value) || value < 0 || value > 0xFFFFFFFF) {
        throw new Error("IPv4 integer must be between 0 and 4294967295.");
    }

    return [
        (value >>> 24) & 255,
        (value >>> 16) & 255,
        (value >>> 8) & 255,
        value & 255,
    ].join(".");
}

function ipv4ToBinary(address) {
    return address
        .split(".")
        .map((octet) => {
            const value = Number(octet);
            return value.toString(2).padStart(8, "0");
        })
        .join(".");
}

// ---------------------------------------------------------------------------
// CIDR AND MASK OPERATIONS
// ---------------------------------------------------------------------------

function validatePrefix(prefix) {
    if (!Number.isInteger(prefix) || prefix < 0 || prefix > 32) {
        throw new Error("CIDR prefix must be an integer from 0 through 32.");
    }
}

function prefixToMaskInteger(prefix) {
    validatePrefix(prefix);

    if (prefix === 0) {
        return 0;
    }

    // Use multiplication rather than a 32-bit signed shift for /32.
    return Math.floor(0xFFFFFFFF - (2 ** (32 - prefix) - 1));
}

function prefixToMask(prefix) {
    return integerToIPv4(prefixToMaskInteger(prefix));
}

function maskToPrefix(mask) {
    const value = ipv4ToInteger(mask);
    const binary = value.toString(2).padStart(32, "0");

    // Valid subnet masks contain all 1s before all 0s.
    if (binary.includes("01")) {
        throw new Error(`${mask} is not a valid contiguous subnet mask.`);
    }

    return binary.split("").filter((bit) => bit === "1").length;
}

function wildcardMask(prefix) {
    const mask = prefixToMaskInteger(prefix);
    return (0xFFFFFFFF - mask) >>> 0;
}

function parseCIDR(cidr) {
    if (typeof cidr !== "string") {
        throw new TypeError("CIDR must be a string.");
    }

    const parts = cidr.split("/");

    if (parts.length !== 2) {
        throw new Error(`Invalid CIDR notation: ${cidr}`);
    }

    const address = parts[0];
    const prefix = Number(parts[1]);

    validatePrefix(prefix);

    const ip = ipv4ToInteger(address);
    const mask = prefixToMaskInteger(prefix);

    // Fundamental subnet calculation:
    // network = IP address AND subnet mask.
    const network = (ip & mask) >>> 0;

    const wildcard = wildcardMask(prefix);
    const broadcast = (network | wildcard) >>> 0;

    return {
        input: cidr,
        address,
        prefix,
        ip,
        mask,
        network,
        broadcast,
        totalAddresses: 2 ** (32 - prefix),
    };
}

// ---------------------------------------------------------------------------
// HOST COUNTS AND RANGES
// ---------------------------------------------------------------------------

function conventionalUsableHosts(prefix) {
    validatePrefix(prefix);

    if (prefix >= 31) {
        return 0;
    }

    return (2 ** (32 - prefix)) - 2;
}

function rfc3021AwareHosts(prefix) {
    validatePrefix(prefix);

    if (prefix === 31) {
        return 2;
    }

    if (prefix === 32) {
        return 1;
    }

    return conventionalUsableHosts(prefix);
}

function networkRange(cidr) {
    const network = parseCIDR(cidr);

    return {
        networkAddress: integerToIPv4(network.network),
        broadcastAddress: integerToIPv4(network.broadcast),
        firstAddress: integerToIPv4(network.network),
        lastAddress: integerToIPv4(network.broadcast),
        conventionalFirstHost:
            network.prefix < 31
                ? integerToIPv4(network.network + 1)
                : integerToIPv4(network.network),
        conventionalLastHost:
            network.prefix < 31
                ? integerToIPv4(network.broadcast - 1)
                : integerToIPv4(network.broadcast),
        totalAddresses: network.totalAddresses,
        usableHosts: conventionalUsableHosts(network.prefix),
        specialAwareHosts: rfc3021AwareHosts(network.prefix),
    };
}

function analyzeCIDR(cidr) {
    const network = parseCIDR(cidr);
    const range = networkRange(cidr);

    return {
        cidr: `${integerToIPv4(network.network)}/${network.prefix}`,
        subnetMask: prefixToMask(network.prefix),
        wildcardMask: integerToIPv4(wildcardMask(network.prefix)),
        ...range,
    };
}

// ---------------------------------------------------------------------------
// SUBNET MEMBERSHIP AND OVERLAP
// ---------------------------------------------------------------------------

function isAddressInNetwork(address, cidr) {
    const ip = ipv4ToInteger(address);
    const network = parseCIDR(cidr);

    return (
        ip >= network.network &&
        ip <= network.broadcast
    );
}

function networkContainsNetwork(parentCIDR, childCIDR) {
    const parent = parseCIDR(parentCIDR);
    const child = parseCIDR(childCIDR);

    return (
        child.network >= parent.network &&
        child.broadcast <= parent.broadcast
    );
}

function networksOverlap(firstCIDR, secondCIDR) {
    const first = parseCIDR(firstCIDR);
    const second = parseCIDR(secondCIDR);

    return (
        first.network <= second.broadcast &&
        second.network <= first.broadcast
    );
}

// ---------------------------------------------------------------------------
// FIXED-LENGTH SUBNETTING
// ---------------------------------------------------------------------------

function splitNetwork(cidr, newPrefix) {
    const parent = parseCIDR(cidr);
    validatePrefix(newPrefix);

    if (newPrefix < parent.prefix) {
        throw new Error(
            "Child prefix cannot be shorter than the parent prefix."
        );
    }

    const count = 2 ** (newPrefix - parent.prefix);
    const blockSize = 2 ** (32 - newPrefix);

    const result = [];

    for (let index = 0; index < count; index += 1) {
        const network = parent.network + (index * blockSize);

        result.push({
            cidr: `${integerToIPv4(network)}/${newPrefix}`,
            networkAddress: integerToIPv4(network),
            broadcastAddress: integerToIPv4(network + blockSize - 1),
            totalAddresses: blockSize,
            usableHosts: conventionalUsableHosts(newPrefix),
        });
    }

    return result;
}

// ---------------------------------------------------------------------------
// VLSM
// ---------------------------------------------------------------------------

function prefixForHostRequirement(hostRequirement) {
    if (!Number.isInteger(hostRequirement) || hostRequirement < 1) {
        throw new Error("Host requirement must be a positive integer.");
    }

    for (let prefix = 30; prefix >= 0; prefix -= 1) {
        if (conventionalUsableHosts(prefix) >= hostRequirement) {
            return prefix;
        }
    }

    throw new Error("Host requirement cannot be represented by IPv4.");
}

function allocateVLSM(parentCIDR, requirements) {
    const parent = parseCIDR(parentCIDR);

    if (!Array.isArray(requirements) || requirements.length === 0) {
        throw new Error("At least one VLSM requirement is required.");
    }

    const sorted = [...requirements].sort(
        (a, b) => b.hosts - a.hosts
    );

    let cursor = parent.network;
    const allocations = [];

    for (const requirement of sorted) {
        if (!requirement.name || !Number.isInteger(requirement.hosts)) {
            throw new Error("Each requirement needs a name and integer hosts.");
        }

        const prefix = prefixForHostRequirement(requirement.hosts);
        const blockSize = 2 ** (32 - prefix);

        // CIDR blocks must begin on boundaries aligned with their block size.
        const remainder = cursor % blockSize;

        if (remainder !== 0) {
            cursor += blockSize - remainder;
        }

        const candidateNetwork = cursor;
        const candidateBroadcast = candidateNetwork + blockSize - 1;

        if (
            candidateNetwork < parent.network ||
            candidateBroadcast > parent.broadcast
        ) {
            throw new Error(
                `Requirement "${requirement.name}" does not fit in ${parentCIDR}.`
            );
        }

        allocations.push({
            name: requirement.name,
            requestedHosts: requirement.hosts,
            cidr: `${integerToIPv4(candidateNetwork)}/${prefix}`,
            networkAddress: integerToIPv4(candidateNetwork),
            broadcastAddress: integerToIPv4(candidateBroadcast),
            usableHosts: conventionalUsableHosts(prefix),
        });

        cursor = candidateBroadcast + 1;
    }

    return allocations;
}

// ---------------------------------------------------------------------------
// ROUTE SUMMARIZATION
// ---------------------------------------------------------------------------

function cidrBlockToRange(cidr) {
    const network = parseCIDR(cidr);

    return {
        start: network.network,
        end: network.broadcast,
    };
}

function commonPrefixLength(first, second) {
    const difference = (first ^ second) >>> 0;

    if (difference === 0) {
        return 32;
    }

    return Math.clz32(difference);
}

function summarizeTwoNetworks(firstCIDR, secondCIDR) {
    const first = parseCIDR(firstCIDR);
    const second = parseCIDR(secondCIDR);

    const minAddress = Math.min(first.network, second.network);
    const maxAddress = Math.max(first.broadcast, second.broadcast);

    const prefix = commonPrefixLength(minAddress, maxAddress);

    const mask = prefixToMaskInteger(prefix);
    const summarizedNetwork = (minAddress & mask) >>> 0;
    const summarizedBroadcast =
        (summarizedNetwork + (2 ** (32 - prefix)) - 1) >>> 0;

    // The result is a valid summary only if it covers exactly the supplied
    // address space without extending beyond the desired combined range.
    const exact =
        summarizedNetwork === minAddress &&
        summarizedBroadcast === maxAddress;

    if (!exact) {
        return null;
    }

    return `${integerToIPv4(summarizedNetwork)}/${prefix}`;
}

function summarizeCIDRs(cidrs) {
    /*
     * A full production-grade route aggregation engine may need to repeatedly
     * merge aligned adjacent prefixes. This implementation performs repeated
     * pairwise merging until no further exact merge is possible.
     */
    let networks = [...cidrs];

    let changed = true;

    while (changed) {
        changed = false;

        networks.sort((a, b) => {
            return (
                parseCIDR(a).network -
                parseCIDR(b).network
            );
        });

        const next = [];
        let index = 0;

        while (index < networks.length) {
            if (index + 1 < networks.length) {
                const merged = summarizeTwoNetworks(
                    networks[index],
                    networks[index + 1]
                );

                if (merged !== null) {
                    next.push(merged);
                    index += 2;
                    changed = true;
                    continue;
                }
            }

            next.push(networks[index]);
            index += 1;
        }

        networks = next;
    }

    return networks;
}

// ---------------------------------------------------------------------------
// LONGEST-PREFIX MATCHING
// ---------------------------------------------------------------------------

function longestPrefixMatch(destination, routes) {
    const address = ipv4ToInteger(destination);

    const matches = routes.filter((route) => {
        const network = parseCIDR(route.cidr);

        return (
            address >= network.network &&
            address <= network.broadcast
        );
    });

    if (matches.length === 0) {
        return null;
    }

    // Routing chooses the most specific matching route.
    matches.sort(
        (a, b) =>
            parseCIDR(b.cidr).prefix -
            parseCIDR(a.cidr).prefix
    );

    return matches[0];
}

// ---------------------------------------------------------------------------
// DISPLAY HELPERS
// ---------------------------------------------------------------------------

function printAnalysis(cidr) {
    const result = analyzeCIDR(cidr);

    console.log(`\nCIDR analysis: ${cidr}`);
    console.log("-".repeat(70));

    for (const [key, value] of Object.entries(result)) {
        console.log(`${key.padEnd(24)}: ${value}`);
    }
}

function printSubnets(cidr, newPrefix) {
    const subnets = splitNetwork(cidr, newPrefix);

    console.log(
        `\n${cidr} split into /${newPrefix} subnets`
    );
    console.log("-".repeat(70));

    subnets.forEach((subnet, index) => {
        console.log(
            `${String(index + 1).padStart(3)}. ` +
            `${subnet.cidr.padEnd(20)} ` +
            `network=${subnet.networkAddress.padEnd(15)} ` +
            `broadcast=${subnet.broadcastAddress.padEnd(15)} ` +
            `hosts=${subnet.usableHosts}`
        );
    });
}

function printVLSM(parentCIDR, requirements) {
    const allocations = allocateVLSM(parentCIDR, requirements);

    console.log(`\nVLSM plan for ${parentCIDR}`);
    console.log("-".repeat(95));

    allocations.forEach((allocation) => {
        console.log(
            `${allocation.name.padEnd(16)} ` +
            `requested=${String(allocation.requestedHosts).padStart(5)} ` +
            `network=${allocation.cidr.padEnd(18)} ` +
            `usable=${String(allocation.usableHosts).padStart(5)} ` +
            `range=${allocation.networkAddress} - ${allocation.broadcastAddress}`
        );
    });
}

// ---------------------------------------------------------------------------
// VALIDATION DEMONSTRATION
// ---------------------------------------------------------------------------

function demonstrateValidation() {
    const examples = [
        "192.168.1.0/24",
        "10.0.0.0/8",
        "172.16.10.50/16",
        "192.168.1.0/33",
        "192.168.1.256/24",
        "not-an-ip/24",
    ];

    console.log("\nCIDR validation");
    console.log("-".repeat(70));

    for (const cidr of examples) {
        try {
            const parsed = parseCIDR(cidr);

            console.log(
                `${cidr.padEnd(25)} -> valid, normalized network ` +
                `${integerToIPv4(parsed.network)}/${parsed.prefix}`
            );
        } catch (error) {
            console.log(
                `${cidr.padEnd(25)} -> invalid: ${error.message}`
            );
        }
    }
}

// ---------------------------------------------------------------------------
// PRACTICAL NETWORK CASE STUDY
// ---------------------------------------------------------------------------

function enterpriseCaseStudy() {
    /*
     * An organization receives 10.50.0.0/16.
     *
     * VLSM is appropriate because departments have different host
     * requirements. A single /24 for every department would waste addresses.
     */
    const requirements = [
        { name: "Engineering", hosts: 500 },
        { name: "Operations", hosts: 200 },
        { name: "Guest-WiFi", hosts: 100 },
        { name: "Servers", hosts: 60 },
        { name: "Finance", hosts: 30 },
        { name: "Network-P2P", hosts: 2 },
    ];

    printVLSM("10.50.0.0/16", requirements);
}

// ---------------------------------------------------------------------------
// TESTS
// ---------------------------------------------------------------------------

function assert(condition, message) {
    if (!condition) {
        throw new Error(`Assertion failed: ${message}`);
    }
}

function runTests() {
    assert(
        prefixToMask(24) === "255.255.255.0",
        "prefix /24 must produce 255.255.255.0"
    );

    assert(
        maskToPrefix("255.255.255.0") === 24,
        "255.255.255.0 must be /24"
    );

    assert(
        ipv4ToBinary("192.168.1.1") ===
            "11000000.10101000.00000001.00000001",
        "binary conversion"
    );

    const analysis = analyzeCIDR("192.168.10.77/26");

    assert(
        analysis.networkAddress === "192.168.10.64",
        "network calculation"
    );

    assert(
        analysis.broadcastAddress === "192.168.10.127",
        "broadcast calculation"
    );

    assert(
        conventionalUsableHosts(24) === 254,
        "traditional /24 host count"
    );

    assert(
        rfc3021AwareHosts(31) === 2,
        "/31 point-to-point host count"
    );

    assert(
        rfc3021AwareHosts(32) === 1,
        "/32 address count"
    );

    assert(
        splitNetwork("192.168.1.0/24", 26).length === 4,
        "four /26 networks fit in /24"
    );

    assert(
        isAddressInNetwork("192.168.1.100", "192.168.1.0/24"),
        "address membership"
    );

    assert(
        !isAddressInNetwork("192.168.2.100", "192.168.1.0/24"),
        "negative membership"
    );

    assert(
        networksOverlap(
            "192.168.0.0/24",
            "192.168.0.128/25"
        ),
        "overlap detection"
    );

    assert(
        networkContainsNetwork(
            "10.0.0.0/8",
            "10.20.0.0/16"
        ),
        "network containment"
    );

    const summary = summarizeCIDRs([
        "192.168.0.0/25",
        "192.168.0.128/25",
    ]);

    assert(
        summary.length === 1 &&
            summary[0] === "192.168.0.0/24",
        "route summarization"
    );

    const routes = [
        { cidr: "0.0.0.0/0", nextHop: "Internet" },
        { cidr: "10.0.0.0/8", nextHop: "Router-A" },
        { cidr: "10.20.0.0/16", nextHop: "Router-B" },
        { cidr: "10.20.30.0/24", nextHop: "Router-C" },
    ];

    const selected = longestPrefixMatch(
        "10.20.30.50",
        routes
    );

    assert(
        selected !== null &&
            selected.nextHop === "Router-C",
        "longest-prefix matching"
    );

    console.log("\nAll JavaScript tests passed.");
}

// ---------------------------------------------------------------------------
// MAIN
// ---------------------------------------------------------------------------

function main() {
    console.log("=".repeat(80));
    console.log("SUBNETTING AND CIDR - JAVASCRIPT STUDY PROGRAM");
    console.log("=".repeat(80));

    console.log("\n1. Binary representation");
    console.log(
        "192.168.10.77 ->",
        ipv4ToBinary("192.168.10.77")
    );

    console.log("\n2. CIDR analysis");
    printAnalysis("192.168.10.77/26");

    console.log("\n3. Fixed-length subnetting");
    printSubnets("192.168.50.0/24", 26);

    console.log("\n4. Validation");
    demonstrateValidation();

    console.log("\n5. Membership and overlap");
    console.log(
        "192.168.1.100 in 192.168.1.0/24:",
        isAddressInNetwork(
            "192.168.1.100",
            "192.168.1.0/24"
        )
    );

    console.log(
        "Networks overlap:",
        networksOverlap(
            "192.168.1.0/24",
            "192.168.1.128/25"
        )
    );

    console.log("\n6. VLSM");
    enterpriseCaseStudy();

    console.log("\n7. Route summarization");
    const summarized = summarizeCIDRs([
        "10.100.0.0/24",
        "10.100.1.0/24",
        "10.100.2.0/24",
        "10.100.3.0/24",
    ]);

    console.log(summarized);

    console.log("\n8. Longest-prefix matching");

    const routes = [
        { cidr: "0.0.0.0/0", nextHop: "Internet gateway" },
        { cidr: "10.0.0.0/8", nextHop: "Core A" },
        { cidr: "10.20.0.0/16", nextHop: "Core B" },
        { cidr: "10.20.30.0/24", nextHop: "Distribution C" },
        { cidr: "10.20.30.128/25", nextHop: "Access D" },
    ];

    [
        "8.8.8.8",
        "10.1.2.3",
        "10.20.5.10",
        "10.20.30.25",
        "10.20.30.200",
    ].forEach((destination) => {
        const route = longestPrefixMatch(destination, routes);

        console.log(
            `${destination.padEnd(16)} -> ` +
            `${route ? route.cidr : "no route"} -> ` +
            `${route ? route.nextHop : "none"}`
        );
    });

    console.log("\n9. Verification");
    runTests();

    console.log("\nStudy program completed.");
}

main();
