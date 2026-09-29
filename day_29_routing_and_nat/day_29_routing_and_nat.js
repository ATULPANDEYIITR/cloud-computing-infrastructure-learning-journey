"use strict";

/*
 * Routing and NAT
 *
 * This standalone JavaScript study file models:
 *   - IPv4 addresses and CIDR networks
 *   - routing tables
 *   - longest-prefix matching
 *   - default gateways
 *   - router forwarding
 *   - TTL
 *   - NAT/PAT
 *   - private-to-public communication
 *   - traceroute concepts
 *   - routing failures
 *   - diagnostic reasoning
 *
 * It uses only standard JavaScript and can run with:
 *     node routing_nat.js
 *
 * The network is simulated so that no privileged networking operations are
 * required.
 */

// ============================================================================
// 1. GENERAL UTILITIES
// ============================================================================

function section(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}

function subsection(title) {
    console.log(`\n--- ${title} ---`);
}

function assert(condition, message) {
    if (!condition) {
        throw new Error(`Assertion failed: ${message}`);
    }
}

function formatIPv4(value) {
    return [
        (value >>> 24) & 255,
        (value >>> 16) & 255,
        (value >>> 8) & 255,
        value & 255
    ].join(".");
}

// Convert dotted IPv4 text to an unsigned 32-bit integer.
function ipv4ToInt(address) {
    const parts = address.split(".");

    if (parts.length !== 4) {
        throw new Error(`Invalid IPv4 address: ${address}`);
    }

    let value = 0;

    for (const part of parts) {
        if (!/^\d+$/.test(part)) {
            throw new Error(`Invalid IPv4 octet: ${part}`);
        }

        const octet = Number(part);

        if (octet < 0 || octet > 255) {
            throw new Error(`IPv4 octet out of range: ${part}`);
        }

        value = ((value << 8) | octet) >>> 0;
    }

    return value >>> 0;
}

function prefixToMask(prefixLength) {
    if (!Number.isInteger(prefixLength) || prefixLength < 0 || prefixLength > 32) {
        throw new Error(`Invalid prefix length: ${prefixLength}`);
    }

    if (prefixLength === 0) {
        return 0;
    }

    return (0xFFFFFFFF << (32 - prefixLength)) >>> 0;
}

function parseCIDR(cidr) {
    const parts = cidr.split("/");

    if (parts.length !== 2) {
        throw new Error(`Invalid CIDR: ${cidr}`);
    }

    const address = ipv4ToInt(parts[0]);
    const prefixLength = Number(parts[1]);
    const mask = prefixToMask(prefixLength);
    const network = (address & mask) >>> 0;

    return {
        cidr,
        network,
        prefixLength,
        mask
    };
}

function ipInNetwork(ip, network) {
    return ((ipv4ToInt(ip) & network.mask) >>> 0) === network.network;
}

function networkText(network) {
    return `${formatIPv4(network.network)}/${network.prefixLength}`;
}

// ============================================================================
// 2. ADDRESSING AND CIDR
// ============================================================================

function demonstrateAddressing() {
    section("1. IPv4 Addressing and CIDR");

    const examples = [
        ["192.168.1.10", "192.168.1.0/24"],
        ["10.20.30.40", "10.0.0.0/8"],
        ["172.16.5.20", "172.16.0.0/12"],
        ["8.8.8.8", "0.0.0.0/0"]
    ];

    for (const [address, cidr] of examples) {
        const network = parseCIDR(cidr);

        console.log(
            `${address.padEnd(16)} in ` +
            `${networkText(network).padEnd(18)} = ` +
            `${ipInNetwork(address, network)}`
        );
    }

    subsection("Private IPv4 address ranges");

    for (const cidr of [
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16"
    ]) {
        console.log(`${cidr} is RFC 1918 private address space.`);
    }

    subsection("Prefix meaning");

    for (const prefix of [8, 16, 24, 30, 32]) {
        const mask = prefixToMask(prefix);
        console.log(
            `/${prefix}`.padEnd(5),
            "mask =",
            formatIPv4(mask),
            "addresses =",
            2 ** (32 - prefix)
        );
    }

    console.log(
        "\nCIDR notation combines an IPv4 address with a prefix length. "
        "The prefix determines which bits identify the network."
    );
}

// ============================================================================
// 3. ROUTING TABLE
// ============================================================================

class Route {
    constructor(networkCIDR, nextHop, interfaceName, metric = 100, description = "") {
        this.network = parseCIDR(networkCIDR);
        this.nextHop = nextHop;
        this.interfaceName = interfaceName;
        this.metric = metric;
        this.description = description;
    }

    matches(destination) {
        return ipInNetwork(destination, this.network);
    }
}

function routeComparator(a, b) {
    if (a.network.prefixLength !== b.network.prefixLength) {
        return b.network.prefixLength - a.network.prefixLength;
    }

    return a.metric - b.metric;
}

function chooseRoute(routes, destination) {
    const matches = routes
        .filter(route => route.matches(destination))
        .sort(routeComparator);

    return matches.length > 0 ? matches[0] : null;
}

function displayRoute(route) {
    return (
        `${networkText(route.network).padEnd(18)} ` +
        `via ${(route.nextHop ?? "direct").padEnd(15)} ` +
        `dev ${route.interfaceName.padEnd(8)} ` +
        `metric=${route.metric}`
    );
}

function demonstrateRoutingTables() {
    section("2. Routing Tables and Longest-Prefix Matching");

    const routes = [
        new Route(
            "0.0.0.0/0",
            "192.168.1.1",
            "eth0",
            100,
            "default"
        ),
        new Route(
            "10.0.0.0/8",
            "192.168.1.254",
            "eth1",
            100,
            "enterprise"
        ),
        new Route(
            "10.10.0.0/16",
            "192.168.1.253",
            "eth2",
            100,
            "regional"
        ),
        new Route(
            "10.10.20.0/24",
            "192.168.1.252",
            "eth3",
            50,
            "specific"
        )
    ];

    for (const route of routes) {
        console.log(displayRoute(route));
    }

    subsection("Route selection");

    for (const destination of [
        "10.10.20.55",
        "10.10.40.10",
        "10.50.1.1",
        "8.8.8.8"
    ]) {
        const selected = chooseRoute(routes, destination);

        if (selected) {
            console.log(
                `${destination.padEnd(16)} -> ` +
                `${networkText(selected.network)} via ` +
                `${selected.nextHop ?? "direct"} dev ${selected.interfaceName}`
            );
        } else {
            console.log(`${destination} -> no route`);
        }
    }

    console.log(
        "\nThe longest matching prefix wins. A /24 is more specific than a "
        "/16, a /16 is more specific than a /8, and /0 is the fallback."
    );
}

// ============================================================================
// 4. PACKETS AND ROUTERS
// ============================================================================

class Packet {
    constructor({
        sourceIP,
        destinationIP,
        sourcePort = null,
        destinationPort = null,
        protocol = "TCP",
        ttl = 64,
        payload = ""
    }) {
        this.sourceIP = sourceIP;
        this.destinationIP = destinationIP;
        this.sourcePort = sourcePort;
        this.destinationPort = destinationPort;
        this.protocol = protocol;
        this.ttl = ttl;
        this.payload = payload;
    }

    clone() {
        return new Packet({
            sourceIP: this.sourceIP,
            destinationIP: this.destinationIP,
            sourcePort: this.sourcePort,
            destinationPort: this.destinationPort,
            protocol: this.protocol,
            ttl: this.ttl,
            payload: this.payload
        });
    }

    summary() {
        const ports =
            this.sourcePort !== null && this.destinationPort !== null
                ? `:${this.sourcePort} -> :${this.destinationPort}`
                : "";

        return (
            `${this.protocol} ${this.sourceIP}${ports} -> ` +
            `${this.destinationIP} TTL=${this.ttl}`
        );
    }
}

class Router {
    constructor(name) {
        this.name = name;
        this.routes = [];
        this.forwardingEnabled = true;
    }

    addRoute(networkCIDR, nextHop, interfaceName, metric = 100, description = "") {
        this.routes.push(
            new Route(
                networkCIDR,
                nextHop,
                interfaceName,
                metric,
                description
            )
        );
    }

    lookup(destination) {
        return chooseRoute(this.routes, destination);
    }

    forward(packet) {
        if (!this.forwardingEnabled) {
            throw new Error(`${this.name}: forwarding is disabled`);
        }

        if (packet.ttl <= 1) {
            throw new Error(`${this.name}: TTL expired`);
        }

        packet.ttl -= 1;

        const route = this.lookup(packet.destinationIP);

        if (!route) {
            throw new Error(
                `${this.name}: no route to ${packet.destinationIP}`
            );
        }

        return route;
    }

    printRoutingTable() {
        console.log(`\nRouting table: ${this.name}`);

        for (const route of [...this.routes].sort(routeComparator)) {
            console.log(displayRoute(route));
        }
    }
}

function demonstrateRouterForwarding() {
    section("3. Router Forwarding");

    const router = new Router("R1");

    router.addRoute(
        "192.168.10.0/24",
        null,
        "lan0",
        0,
        "direct LAN"
    );

    router.addRoute(
        "192.168.20.0/24",
        null,
        "lan1",
        0,
        "server LAN"
    );

    router.addRoute(
        "0.0.0.0/0",
        "192.168.10.254",
        "wan0",
        100,
        "default"
    );

    router.printRoutingTable();

    const packet = new Packet({
        sourceIP: "192.168.10.50",
        destinationIP: "192.168.20.80",
        sourcePort: 50000,
        destinationPort: 443,
        protocol: "TCP"
    });

    console.log("\nBefore:", packet.summary());

    const route = router.forward(packet);

    console.log(
        "Selected:",
        `${networkText(route.network)} via ${route.nextHop ?? "direct"}`
    );

    console.log("After:", packet.summary());

    console.log(
        "\nRouters use Layer-3 routing information to determine where an "
        "IP packet should be forwarded."
    );
}

// ============================================================================
// 5. DEFAULT GATEWAY
// ============================================================================

class Host {
    constructor(name, address, networkCIDR, gateway) {
        this.name = name;
        this.address = address;
        this.network = parseCIDR(networkCIDR);
        this.gateway = gateway;
    }

    needsGateway(destination) {
        return !ipInNetwork(destination, this.network);
    }

    nextHop(destination) {
        return this.needsGateway(destination)
            ? this.gateway
            : destination;
    }
}

function demonstrateDefaultGateway() {
    section("4. Default Gateway");

    const host = new Host(
        "Client",
        "192.168.1.50",
        "192.168.1.0/24",
        "192.168.1.1"
    );

    for (const destination of [
        "192.168.1.75",
        "192.168.2.75",
        "8.8.8.8"
    ]) {
        if (host.needsGateway(destination)) {
            console.log(
                `${destination}: outside ${networkText(host.network)} -> ` +
                `gateway ${host.gateway}`
            );
        } else {
            console.log(
                `${destination}: directly reachable on ` +
                `${networkText(host.network)}`
            );
        }
    }

    console.log(
        "\nThe default gateway is a fallback next hop. A host does not "
        + "send every packet to the gateway; local destinations can be "
        + "reached directly at Layer 3."
    );
}

// ============================================================================
// 6. NAT/PAT
// ============================================================================

class NatMapping {
    constructor(
        privateIP,
        privatePort,
        publicIP,
        publicPort,
        remoteIP,
        remotePort,
        protocol
    ) {
        this.privateIP = privateIP;
        this.privatePort = privatePort;
        this.publicIP = publicIP;
        this.publicPort = publicPort;
        this.remoteIP = remoteIP;
        this.remotePort = remotePort;
        this.protocol = protocol;
        this.createdAt = Date.now();
        this.packetCount = 0;
    }

    privateEndpoint() {
        return `${this.privateIP}:${this.privatePort}`;
    }

    publicEndpoint() {
        return `${this.publicIP}:${this.publicPort}`;
    }
}

class PATGateway {
    constructor(publicIP, firstPort = 40000, lastPort = 49999) {
        this.publicIP = publicIP;
        this.firstPort = firstPort;
        this.lastPort = lastPort;
        this.nextPort = firstPort;
        this.outbound = new Map();
        this.inbound = new Map();
    }

    flowKey(packet) {
        return [
            packet.sourceIP,
            packet.sourcePort,
            packet.destinationIP,
            packet.destinationPort,
            packet.protocol
        ].join("|");
    }

    inboundKey(publicPort, protocol) {
        return `${this.publicIP}|${publicPort}|${protocol}`;
    }

    allocatePort() {
        const maximumAttempts = this.lastPort - this.firstPort + 1;

        for (let attempt = 0; attempt < maximumAttempts; attempt++) {
            const port = this.nextPort;

            this.nextPort += 1;

            if (this.nextPort > this.lastPort) {
                this.nextPort = this.firstPort;
            }

            const key = this.inboundKey(port, "TCP");

            if (!this.inbound.has(key)) {
                return port;
            }
        }

        throw new Error("NAT port pool exhausted");
    }

    translateOutbound(packet) {
        if (packet.sourcePort === null || packet.destinationPort === null) {
            throw new Error("PAT requires transport-layer ports");
        }

        const key = this.flowKey(packet);
        let mapping = this.outbound.get(key);

        if (!mapping) {
            const publicPort = this.allocatePort();

            mapping = new NatMapping(
                packet.sourceIP,
                packet.sourcePort,
                this.publicIP,
                publicPort,
                packet.destinationIP,
                packet.destinationPort,
                packet.protocol
            );

            this.outbound.set(key, mapping);
            this.inbound.set(
                this.inboundKey(publicPort, packet.protocol),
                mapping
            );
        }

        mapping.packetCount += 1;

        const translated = packet.clone();

        translated.sourceIP = this.publicIP;
        translated.sourcePort = mapping.publicPort;

        return translated;
    }

    translateInbound(packet) {
        if (packet.destinationPort === null) {
            throw new Error("Inbound PAT requires a destination port");
        }

        const mapping = this.inbound.get(
            this.inboundKey(
                packet.destinationPort,
                packet.protocol
            )
        );

        if (!mapping) {
            throw new Error("No matching NAT state");
        }

        const translated = packet.clone();

        translated.destinationIP = mapping.privateIP;
        translated.destinationPort = mapping.privatePort;

        return translated;
    }

    printTable() {
        console.log("\nPAT translation table");

        if (this.outbound.size === 0) {
            console.log("(empty)");
            return;
        }

        for (const mapping of this.outbound.values()) {
            console.log(
                `${mapping.privateEndpoint().padEnd(22)} -> ` +
                `${mapping.publicEndpoint().padEnd(22)} -> ` +
                `${mapping.remoteIP}:${mapping.remotePort} ` +
                `${mapping.protocol} packets=${mapping.packetCount}`
            );
        }
    }
}

function demonstrateNAT() {
    section("5. NAT and PAT");

    const nat = new PATGateway("203.0.113.10");

    const packets = [
        new Packet({
            sourceIP: "192.168.1.10",
            destinationIP: "93.184.216.34",
            sourcePort: 51000,
            destinationPort: 443
        }),
        new Packet({
            sourceIP: "192.168.1.11",
            destinationIP: "93.184.216.34",
            sourcePort: 51001,
            destinationPort: 443
        }),
        new Packet({
            sourceIP: "192.168.1.10",
            destinationIP: "142.250.72.14",
            sourcePort: 51002,
            destinationPort: 443
        })
    ];

    const translatedPackets = [];

    for (const packet of packets) {
        const translated = nat.translateOutbound(packet);

        translatedPackets.push(translated);

        console.log("Before:", packet.summary());
        console.log("After :", translated.summary());
        console.log();
    }

    nat.printTable();

    const response = new Packet({
        sourceIP: "93.184.216.34",
        destinationIP: translatedPackets[0].sourceIP,
        sourcePort: 443,
        destinationPort: translatedPackets[0].sourcePort
    });

    const restored = nat.translateInbound(response);

    console.log("\nInbound response before reverse NAT:");
    console.log(response.summary());

    console.log("Inbound response after reverse NAT:");
    console.log(restored.summary());

    console.log(
        "\nPAT permits many private flows to share one public IPv4 address "
        + "by assigning distinct public transport ports."
    );
}

// ============================================================================
// 7. NAT TYPES
// ============================================================================

function explainNATTypes() {
    section("6. NAT Classifications");

    const types = [
        [
            "Static NAT",
            "Stable one-to-one private/public mapping",
            "Consistent address publishing"
        ],
        [
            "Dynamic NAT",
            "Temporary mapping from a public address pool",
            "Organizations with public address pools"
        ],
        [
            "PAT/NAPT",
            "Many flows share public IPs using ports",
            "Typical IPv4 Internet access"
        ],
        [
            "SNAT",
            "Source address/port rewritten",
            "Outbound translation"
        ],
        [
            "DNAT",
            "Destination address/port rewritten",
            "Inbound publishing/port forwarding"
        ]
    ];

    for (const [name, mechanism, use] of types) {
        console.log(`${name}: ${mechanism}`);
        console.log(`  Use: ${use}\n`);
    }

    console.log(
        "NAT does not eliminate the need for routing. The gateway still "
        + "requires routes to determine where translated packets travel."
    );
}

// ============================================================================
// 8. END-TO-END PRIVATE-TO-PUBLIC SIMULATION
// ============================================================================

class NetworkSimulation {
    constructor() {
        this.routers = new Map();
        this.hosts = new Map();
        this.links = [];
        this.nat = null;
    }

    addRouter(router) {
        this.routers.set(router.name, router);
    }

    addHost(host) {
        this.hosts.set(host.name, host);
    }

    addLink(left, right, networkCIDR) {
        this.links.push({
            left,
            right,
            network: parseCIDR(networkCIDR)
        });
    }

    printTopology() {
        console.log("\nTopology:");

        for (const link of this.links) {
            console.log(
                `${link.left} <-> ${link.right} ` +
                `[${networkText(link.network)}]`
            );
        }
    }
}

function buildNetwork() {
    const network = new NetworkSimulation();

    const client = new Host(
        "LAN-Client",
        "192.168.50.10",
        "192.168.50.0/24",
        "192.168.50.1"
    );

    const server = new Host(
        "Internet-Server",
        "198.51.100.20",
        "198.51.100.0/24",
        "198.51.100.1"
    );

    const edge = new Router("Edge-Router");

    edge.addRoute(
        "192.168.50.0/24",
        null,
        "lan",
        0,
        "private LAN"
    );

    edge.addRoute(
        "203.0.113.0/30",
        null,
        "wan",
        0,
        "ISP transit"
    );

    edge.addRoute(
        "0.0.0.0/0",
        "203.0.113.1",
        "wan",
        10,
        "Internet default"
    );

    const isp = new Router("ISP-Router");

    isp.addRoute(
        "203.0.113.0/30",
        null,
        "customer",
        0,
        "customer link"
    );

    isp.addRoute(
        "198.51.100.0/24",
        null,
        "internet",
        0,
        "server network"
    );

    network.addHost(client);
    network.addHost(server);
    network.addRouter(edge);
    network.addRouter(isp);

    network.nat = new PATGateway("203.0.113.2");

    network.addLink(
        "LAN-Client",
        "Edge-Router",
        "192.168.50.0/24"
    );

    network.addLink(
        "Edge-Router",
        "ISP-Router",
        "203.0.113.0/30"
    );

    network.addLink(
        "ISP-Router",
        "Internet-Server",
        "198.51.100.0/24"
    );

    return network;
}

function demonstratePrivateToPublicCommunication() {
    section("7. Private-to-Public Communication");

    const network = buildNetwork();

    network.printTopology();

    const client = network.hosts.get("LAN-Client");
    const server = network.hosts.get("Internet-Server");

    const packet = new Packet({
        sourceIP: client.address,
        destinationIP: server.address,
        sourcePort: 52000,
        destinationPort: 443,
        protocol: "TCP",
        ttl: 8,
        payload: "HTTPS request"
    });

    console.log("\n1. Client creates packet:");
    console.log(packet.summary());

    console.log("\n2. Client checks destination:");
    console.log(
        `${server.address} is outside ${networkText(client.network)}`
    );
    console.log(`Next hop: ${client.gateway}`);

    console.log("\n3. Edge router translates source:");
    const translated = network.nat.translateOutbound(packet);
    console.log("Before NAT:", packet.summary());
    console.log("After NAT :", translated.summary());

    const edge = network.routers.get("Edge-Router");
    const edgeRoute = edge.lookup(translated.destinationIP);

    console.log("\n4. Edge router performs route lookup:");
    console.log(displayRoute(edgeRoute));

    const isp = network.routers.get("ISP-Router");
    const ispRoute = isp.lookup(translated.destinationIP);

    console.log("\n5. ISP router performs route lookup:");
    console.log(displayRoute(ispRoute));

    console.log("\n6. Server receives the public packet:");
    console.log(
        `${server.name} receives ${translated.destinationIP}:${translated.destinationPort}`
    );

    const response = new Packet({
        sourceIP: server.address,
        destinationIP: translated.sourceIP,
        sourcePort: 443,
        destinationPort: translated.sourcePort,
        protocol: "TCP",
        ttl: 8,
        payload: "HTTPS response"
    });

    console.log("\n7. Server response reaches public NAT endpoint:");
    console.log(response.summary());

    const restored = network.nat.translateInbound(response);

    console.log("\n8. NAT restores the private destination:");
    console.log(restored.summary());

    console.log(
        "\nLogical path:\n" +
        "private host -> gateway -> NAT -> ISP -> Internet server -> " +
        "ISP -> public NAT endpoint -> reverse NAT -> private host"
    );
}

// ============================================================================
// 9. TRACEROUTE
// ============================================================================

class TraceHop {
    constructor(address, name, delayMs) {
        this.address = address;
        this.name = name;
        this.delayMs = delayMs;
    }
}

function simulateTraceroute(hops, maxHops = 30) {
    const output = [];

    for (let ttl = 1; ttl <= maxHops; ttl++) {
        if (ttl <= hops.length) {
            const hop = hops[ttl - 1];

            if (ttl < hops.length) {
                output.push(
                    `${String(ttl).padStart(2)}  ` +
                    `${hop.address.padEnd(16)} ` +
                    `${hop.delayMs.toFixed(2).padStart(7)} ms  ` +
                    `${hop.name}  ` +
                    "(TTL expired -> ICMP Time Exceeded)"
                );
            } else {
                output.push(
                    `${String(ttl).padStart(2)}  ` +
                    `${hop.address.padEnd(16)} ` +
                    `${hop.delayMs.toFixed(2).padStart(7)} ms  ` +
                    `${hop.name}  (destination reached)`
                );
                break;
            }
        } else {
            output.push(`${String(ttl).padStart(2)}  * * *  no response`);
            break;
        }
    }

    return output;
}

function demonstrateTraceroute() {
    section("8. Traceroute and TTL");

    const hops = [
        new TraceHop("192.168.50.1", "Edge-Router", 1.2),
        new TraceHop("203.0.113.1", "ISP-Router", 8.7),
        new TraceHop("198.51.100.1", "Transit-Router", 17.3),
        new TraceHop("198.51.100.20", "Internet-Server", 22.4)
    ];

    console.log("Simulated traceroute:");

    for (const line of simulateTraceroute(hops)) {
        console.log(line);
    }

    console.log(
        "\nTraceroute infers path information from responses to probes with "
        + "increasing TTL values. It can be incomplete because devices may "
        + "filter, rate-limit, or ignore traceroute-related traffic."
    );
}

// ============================================================================
// 10. ROUTING PROTOCOLS
// ============================================================================

function explainRoutingProtocols() {
    section("9. Static and Dynamic Routing");

    const protocols = [
        [
            "Static",
            "Administrator-configured routes",
            "Small or intentionally controlled topologies"
        ],
        [
            "RIP",
            "Distance-vector, hop-count metric",
            "Historical/small networks"
        ],
        [
            "OSPF",
            "Link-state interior gateway protocol",
            "Enterprise/data-center networks"
        ],
        [
            "IS-IS",
            "Link-state interior gateway protocol",
            "Large infrastructure/service-provider networks"
        ],
        [
            "BGP",
            "Path-vector inter-domain routing",
            "Internet-scale autonomous-system routing"
        ]
    ];

    for (const [name, mechanism, use] of protocols) {
        console.log(`${name}: ${mechanism}`);
        console.log(`  Typical use: ${use}\n`);
    }

    console.log(
        "A routing table contains forwarding information. A routing protocol "
        + "is one method of learning and maintaining routes."
    );
}

// ============================================================================
// 11. EDGE CASES
// ============================================================================

function demonstrateEdgeCases() {
    section("10. Edge Cases and Failure Conditions");

    subsection("No route");

    const routes = [
        new Route("192.168.1.0/24", null, "eth0", 0)
    ];

    console.log(
        "10.0.0.1 ->",
        chooseRoute(routes, "10.0.0.1")
    );

    subsection("Overlapping routes");

    const overlapping = [
        new Route(
            "10.0.0.0/8",
            "192.0.2.1",
            "eth0",
            100
        ),
        new Route(
            "10.10.0.0/16",
            "192.0.2.2",
            "eth1",
            100
        )
    ];

    const selected = chooseRoute(
        overlapping,
        "10.10.5.20"
    );

    console.log(
        "10.10.5.20 selects:",
        displayRoute(selected)
    );

    subsection("Equal prefix, different metric");

    const equalPrefix = [
        new Route(
            "10.20.0.0/16",
            "192.0.2.10",
            "eth0",
            50
        ),
        new Route(
            "10.20.0.0/16",
            "192.0.2.11",
            "eth1",
            100
        )
    ];

    const metricSelected = chooseRoute(
        equalPrefix,
        "10.20.1.1"
    );

    console.log(
        "Selected lower metric:",
        metricSelected.nextHop,
        metricSelected.metric
    );

    subsection("TTL expiration");

    const router = new Router("Failure-Router");

    router.addRoute(
        "0.0.0.0/0",
        "192.0.2.1",
        "wan"
    );

    const packet = new Packet({
        sourceIP: "192.168.1.10",
        destinationIP: "8.8.8.8",
        sourcePort: 50000,
        destinationPort: 443,
        ttl: 1
    });

    try {
        router.forward(packet);
    } catch (error) {
        console.log("Expected failure:", error.message);
    }

    subsection("Missing NAT state");

    const nat = new PATGateway("203.0.113.50");

    const response = new Packet({
        sourceIP: "198.51.100.10",
        destinationIP: "203.0.113.50",
        sourcePort: 443,
        destinationPort: 41000
    });

    try {
        nat.translateInbound(response);
    } catch (error) {
        console.log("Expected failure:", error.message);
    }

    subsection("Operational failure categories");

    for (const failure of [
        "Incorrect subnet prefix",
        "Wrong default gateway",
        "Missing route",
        "Wrong next hop",
        "Routing loop",
        "TTL expiration",
        "NAT state timeout",
        "NAT port exhaustion",
        "Firewall or ACL filtering",
        "Asymmetric routing",
        "MTU problems",
        "DNS failure mistaken for routing failure"
    ]) {
        console.log(`- ${failure}`);
    }
}

// ============================================================================
// 12. PERFORMANCE
// ============================================================================

function discussPerformance() {
    section("11. Performance and Design");

    const topics = {
        "Routing lookup":
            "Routers require efficient longest-prefix matching. Hardware "
            + "tables, TCAM, tries, and optimized software structures can "
            + "reduce forwarding lookup cost.",

        "NAT state":
            "PAT creates state for translated flows. Large gateways need "
            + "efficient state lookup, timers, port allocation, and memory "
            + "management.",

        "Routing convergence":
            "Dynamic routing protocols exchange control-plane information. "
            + "Convergence speed and stability must be balanced.",

        "MTU":
            "Different links may have different maximum transmission units. "
            + "Path-MTU behavior can become important when larger packets fail.",

        "Asymmetry":
            "Forward and return paths may differ. Stateful devices must be "
            + "placed where required flow state remains visible."
    };

    for (const [name, explanation] of Object.entries(topics)) {
        console.log(`\n${name}:`);
        console.log(`  ${explanation}`);
    }
}

// ============================================================================
// 13. SECURITY
// ============================================================================

function discussSecurity() {
    section("12. Security Considerations");

    const topics = [
        [
            "NAT is not a firewall",
            "NAT changes addresses and ports. Explicit security policy is "
            + "normally implemented by firewall/ACL controls."
        ],
        [
            "Private does not mean trusted",
            "RFC 1918 addressing does not authenticate users or systems."
        ],
        [
            "Route manipulation",
            "Unauthorized route changes can redirect or blackhole traffic."
        ],
        [
            "Traceroute visibility",
            "Responding infrastructure can expose aspects of topology."
        ],
        [
            "NAT exhaustion",
            "Excessive flow creation can consume translation state or ports."
        ],
        [
            "Management-plane security",
            "Router configuration and control interfaces require independent "
            + "access protection."
        ]
    ];

    for (const [name, explanation] of topics) {
        console.log(`\n${name}:`);
        console.log(`  ${explanation}`);
    }
}

// ============================================================================
// 14. TROUBLESHOOTING
// ============================================================================

function troubleshootingWorkflow() {
    section("13. Practical Troubleshooting Workflow");

    const steps = [
        "Confirm interface state.",
        "Confirm IP address and prefix.",
        "Confirm destination address.",
        "Determine local versus routed destination.",
        "Inspect the host routing table.",
        "Verify the default gateway.",
        "Test gateway reachability.",
        "Inspect relevant router routing tables.",
        "Check NAT/SNAT/PAT state.",
        "Check firewall and ACL rules.",
        "Use traceroute/tracert to observe the path.",
        "Check DNS independently.",
        "Verify the return route.",
        "Check MTU when packet size appears relevant."
    ];

    steps.forEach((step, index) => {
        console.log(`${index + 1}. ${step}`);
    });

    console.log(
        "\nLinux examples:\n" +
        "  ip addr\n" +
        "  ip route\n" +
        "  ip route get 8.8.8.8\n" +
        "  ping 8.8.8.8\n" +
        "  traceroute 8.8.8.8\n\n" +
        "Windows examples:\n" +
        "  ipconfig\n" +
        "  route print\n" +
        "  ping 8.8.8.8\n" +
        "  tracert 8.8.8.8"
    );
}

// ============================================================================
// 15. ASYNCHRONOUS TRACEROUTE-STYLE OBSERVATION
// ============================================================================

function probeHopAsync(hop, ttl) {
    // The timeout models an observed round-trip delay rather than performing
    // an actual network probe.
    return new Promise(resolve => {
        setTimeout(() => {
            resolve({
                ttl,
                address: hop.address,
                name: hop.name,
                delayMs: hop.delayMs
            });
        }, Math.max(1, Math.round(hop.delayMs)));
    });
}

async function demonstrateAsyncTracing() {
    section("14. JavaScript Asynchronous Network Observation");

    const hops = [
        new TraceHop("192.168.50.1", "Edge-Router", 5),
        new TraceHop("203.0.113.1", "ISP-Router", 8),
        new TraceHop("198.51.100.1", "Transit-Router", 12),
        new TraceHop("198.51.100.20", "Internet-Server", 16)
    ];

    for (let ttl = 1; ttl <= hops.length; ttl++) {
        const result = await probeHopAsync(
            hops[ttl - 1],
            ttl
        );

        console.log(
            `TTL=${result.ttl} ${result.address} ` +
            `${result.delayMs} ms ${result.name}`
        );
    }

    console.log(
        "\nThe asynchronous example demonstrates how JavaScript can model "
        + "I/O-style operations without blocking the event loop."
    );
}

// ============================================================================
// 16. SELF TESTS
// ============================================================================

function runSelfTests() {
    section("15. Built-In Tests");

    const routes = [
        new Route(
            "0.0.0.0/0",
            "192.168.1.1",
            "default",
            100
        ),
        new Route(
            "10.0.0.0/8",
            "192.168.1.2",
            "private",
            100
        ),
        new Route(
            "10.1.0.0/16",
            "192.168.1.3",
            "regional",
            100
        ),
        new Route(
            "10.1.2.0/24",
            "192.168.1.4",
            "local",
            100
        )
    ];

    assert(
        chooseRoute(routes, "10.1.2.99").network.prefixLength === 24,
        "most-specific /24 route"
    );

    assert(
        chooseRoute(routes, "10.1.99.99").network.prefixLength === 16,
        "most-specific /16 route"
    );

    assert(
        chooseRoute(routes, "10.99.99.99").network.prefixLength === 8,
        "most-specific /8 route"
    );

    assert(
        chooseRoute(routes, "8.8.8.8").network.prefixLength === 0,
        "default route"
    );

    const nat = new PATGateway(
        "203.0.113.100",
        40000,
        40010
    );

    const first = new Packet({
        sourceIP: "192.168.1.10",
        destinationIP: "198.51.100.20",
        sourcePort: 50000,
        destinationPort: 443
    });

    const second = new Packet({
        sourceIP: "192.168.1.11",
        destinationIP: "198.51.100.20",
        sourcePort: 50000,
        destinationPort: 443
    });

    const translatedFirst = nat.translateOutbound(first);
    const translatedSecond = nat.translateOutbound(second);

    assert(
        translatedFirst.sourceIP === "203.0.113.100",
        "first public address"
    );

    assert(
        translatedSecond.sourceIP === "203.0.113.100",
        "second public address"
    );

    assert(
        translatedFirst.sourcePort !== translatedSecond.sourcePort,
        "distinct PAT ports"
    );

    const response = new Packet({
        sourceIP: "198.51.100.20",
        destinationIP: "203.0.113.100",
        sourcePort: 443,
        destinationPort: translatedFirst.sourcePort
    });

    const restored = nat.translateInbound(response);

    assert(
        restored.destinationIP === "192.168.1.10",
        "reverse NAT destination"
    );

    assert(
        restored.destinationPort === 50000,
        "reverse NAT port"
    );

    console.log("All JavaScript routing and NAT tests passed.");
}

// ============================================================================
// 17. KNOWLEDGE CHECK
// ============================================================================

function knowledgeCheck() {
    section("16. Knowledge Check");

    const checks = [
        [
            "Which route wins: 10.0.0.0/8 or 10.10.0.0/16?",
            "10.10.0.0/16 because it has the longer prefix."
        ],
        [
            "What is the purpose of a default route?",
            "It is used when no more-specific route matches."
        ],
        [
            "Why does PAT use ports?",
            "Ports distinguish multiple simultaneous translated flows."
        ],
        [
            "What does TTL help prevent?",
            "Indefinite circulation caused by forwarding loops."
        ],
        [
            "Does NAT replace routing?",
            "No. NAT and routing perform different functions."
        ],
        [
            "Is traceroute guaranteed to reveal every router?",
            "No. Filtering, rate limiting, asymmetric routing, and other "
            + "conditions can hide or distort hops."
        ]
    ];

    for (const [question, answer] of checks) {
        console.log(`\n${question}\nAnswer: ${answer}`);
    }
}

// ============================================================================
// 18. MAIN
// ============================================================================

async function main() {
    demonstrateAddressing();
    demonstrateRoutingTables();
    demonstrateRouterForwarding();
    demonstrateDefaultGateway();
    demonstrateNAT();
    explainNATTypes();
    demonstratePrivateToPublicCommunication();
    demonstrateTraceroute();
    explainRoutingProtocols();
    demonstrateEdgeCases();
    discussPerformance();
    discussSecurity();
    troubleshootingWorkflow();
    await demonstrateAsyncTracing();
    runSelfTests();
    knowledgeCheck();

    section("17. Operational Model");

    console.log(
        "Host:\n" +
        "  address -> subnet check -> route lookup -> next hop\n\n" +
        "Router:\n" +
        "  receive -> TTL decrement -> longest-prefix lookup -> policy/NAT -> forward\n\n" +
        "Private-to-public:\n" +
        "  private host -> gateway -> PAT -> public network -> server\n" +
        "  server -> public NAT endpoint -> reverse PAT -> private host\n\n" +
        "Troubleshooting:\n" +
        "  address -> prefix -> gateway -> route -> next hop -> NAT -> ACL -> return path"
    );
}

main().catch(error => {
    console.error("\nFatal error:", error.message);
    process.exitCode = 1;
});
