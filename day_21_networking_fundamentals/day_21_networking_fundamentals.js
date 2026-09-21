/*
 * Networking Fundamentals and Wireshark Concepts
 * =================================================
 *
 * This self-contained JavaScript file demonstrates:
 *
 * - Networks, clients and servers
 * - IP and MAC addresses
 * - Ports and sockets
 * - TCP and UDP
 * - DNS and ARP concepts
 * - Packet structures
 * - Encapsulation
 * - Routing
 * - Firewalls
 * - NAT
 * - TCP handshakes
 * - Packet filtering
 * - Wireshark-style analysis concepts
 * - HTTP and HTTPS concepts
 * - Timing and throughput
 * - Troubleshooting
 *
 * It uses only standard JavaScript features and Node.js built-in modules.
 * It does not require npm packages or perform live packet capture.
 */

"use strict";

const net = require("net");
const dns = require("dns");
const crypto = require("crypto");


// ============================================================================
// BASIC OUTPUT HELPERS
// ============================================================================

function section(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}

function subsection(title) {
    console.log("\n" + "-".repeat(78));
    console.log(title);
    console.log("-".repeat(78));
}


// ============================================================================
// NETWORK TERMINOLOGY
// ============================================================================

section("NETWORKING FUNDAMENTALS");

console.log(`
A network allows devices to exchange information.

Client:
  Requests a service.

Server:
  Provides a service.

Packet:
  A unit of network-layer information.

Frame:
  A link-layer unit that can carry a network-layer packet.

Protocol:
  Rules that define how communicating systems format and interpret data.

Port:
  A logical transport-layer endpoint associated with an application.

Socket:
  A communication endpoint commonly represented by an IP address and port.

Router:
  Forwards traffic between IP networks.

Switch:
  Forwards Ethernet frames inside a local network.

Firewall:
  Applies traffic-control rules.
`);


// ============================================================================
// IP ADDRESS VALIDATION
// ============================================================================

section("IP ADDRESSING");

function isValidIPv4(address) {
    const parts = address.split(".");

    if (parts.length !== 4) {
        return false;
    }

    return parts.every(part => {
        if (part === "" || !/^\d+$/.test(part)) {
            return false;
        }

        const number = Number(part);
        return number >= 0 && number <= 255;
    });
}

function ipv4ToInteger(address) {
    if (!isValidIPv4(address)) {
        throw new Error(`Invalid IPv4 address: ${address}`);
    }

    return address
        .split(".")
        .reduce((result, octet) => (
            result * 256 + Number(octet)
        ), 0);
}

function integerToIPv4(value) {
    if (!Number.isInteger(value) || value < 0 || value > 0xffffffff) {
        throw new Error("IPv4 integer must be between 0 and 2^32 - 1.");
    }

    return [
        (value >>> 24) & 255,
        (value >>> 16) & 255,
        (value >>> 8) & 255,
        value & 255
    ].join(".");
}

for (const address of [
    "192.168.1.10",
    "10.0.0.5",
    "8.8.8.8",
    "256.1.1.1",
    "not-an-ip"
]) {
    console.log(
        `${address.padEnd(18)} valid=${isValidIPv4(address)}`
    );
}

const address = "192.168.1.10";
const integerAddress = ipv4ToInteger(address);

console.log("\nIPv4 conversion:");
console.log("Address :", address);
console.log("Integer :", integerAddress);
console.log("Back    :", integerToIPv4(integerAddress));


// ============================================================================
// CIDR AND SUBNETTING
// ============================================================================

section("CIDR AND SUBNETTING");

function prefixToMask(prefixLength) {
    if (!Number.isInteger(prefixLength) ||
        prefixLength < 0 ||
        prefixLength > 32) {
        throw new Error("Prefix length must be from 0 through 32.");
    }

    if (prefixLength === 0) {
        return 0;
    }

    return (0xffffffff << (32 - prefixLength)) >>> 0;
}

function networkAddress(address, prefixLength) {
    const integer = ipv4ToInteger(address);
    const mask = prefixToMask(prefixLength);
    return integerToIPv4((integer & mask) >>> 0);
}

function broadcastAddress(address, prefixLength) {
    const integer = ipv4ToInteger(address);
    const mask = prefixToMask(prefixLength);
    return integerToIPv4(
        ((integer & mask) | (~mask >>> 0)) >>> 0
    );
}

for (const [ip, prefix] of [
    ["192.168.1.25", 24],
    ["192.168.1.70", 26],
    ["10.20.30.40", 16]
]) {
    console.log(`\n${ip}/${prefix}`);
    console.log("Network  :", networkAddress(ip, prefix));
    console.log("Broadcast:", broadcastAddress(ip, prefix));
}


// ============================================================================
// MAC ADDRESSES
// ============================================================================

section("MAC ADDRESSES");

function normalizeMac(mac) {
    const cleaned = mac
        .replace(/[:-]/g, "")
        .replace(/\./g, "")
        .toLowerCase();

    if (!/^[0-9a-f]{12}$/.test(cleaned)) {
        throw new Error("Invalid MAC address.");
    }

    return cleaned.match(/.{2}/g).join(":");
}

function macToBytes(mac) {
    return Buffer.from(normalizeMac(mac).replace(/:/g, ""), "hex");
}

function bytesToMac(buffer) {
    if (buffer.length !== 6) {
        throw new Error("A MAC address has six bytes.");
    }

    return [...buffer]
        .map(byte => byte.toString(16).padStart(2, "0"))
        .join(":");
}

const mac = normalizeMac("AA-BB-CC-DD-EE-FF");

console.log("Normalized:", mac);
console.log("Bytes     :", macToBytes(mac));
console.log("Recovered :", bytesToMac(macToBytes(mac)));


// ============================================================================
// PORTS
// ============================================================================

section("PORTS");

const commonPorts = new Map([
    [22, "SSH"],
    [25, "SMTP"],
    [53, "DNS"],
    [67, "DHCP server"],
    [68, "DHCP client"],
    [80, "HTTP"],
    [123, "NTP"],
    [161, "SNMP"],
    [443, "HTTPS"],
    [3389, "RDP"]
]);

function describePort(port) {
    if (!Number.isInteger(port) || port < 0 || port > 65535) {
        throw new Error("Port must be an integer from 0 through 65535.");
    }

    if (commonPorts.has(port)) {
        return commonPorts.get(port);
    }

    if (port <= 1023) {
        return "well-known range";
    }

    if (port <= 49151) {
        return "registered range";
    }

    return "dynamic/private range";
}

for (const port of [22, 53, 80, 443, 50000]) {
    console.log(`Port ${String(port).padStart(5)}: ${describePort(port)}`);
}


// ============================================================================
// SOCKET ENDPOINT
// ============================================================================

section("SOCKET ENDPOINTS");

class SocketEndpoint {
    constructor(ipAddress, port, protocol) {
        if (!isValidIPv4(ipAddress)) {
            throw new Error("Invalid IPv4 address.");
        }

        if (!Number.isInteger(port) || port < 0 || port > 65535) {
            throw new Error("Invalid port.");
        }

        const normalizedProtocol = protocol.toUpperCase();

        if (!["TCP", "UDP"].includes(normalizedProtocol)) {
            throw new Error("Protocol must be TCP or UDP.");
        }

        this.ipAddress = ipAddress;
        this.port = port;
        this.protocol = normalizedProtocol;
    }

    toString() {
        return `${this.protocol} ${this.ipAddress}:${this.port}`;
    }
}

const clientEndpoint = new SocketEndpoint(
    "192.168.1.25",
    53142,
    "TCP"
);

const serverEndpoint = new SocketEndpoint(
    "93.184.216.34",
    443,
    "TCP"
);

console.log("Client:", clientEndpoint.toString());
console.log("Server:", serverEndpoint.toString());


// ============================================================================
// PROTOCOL LAYERS
// ============================================================================

section("PROTOCOL LAYERS");

const protocolStack = {
    Application: ["HTTP", "HTTPS", "DNS", "DHCP", "SSH"],
    Transport: ["TCP", "UDP"],
    Internet: ["IPv4", "IPv6", "ICMP"],
    Link: ["Ethernet", "Wi-Fi", "ARP"]
};

for (const [layer, protocols] of Object.entries(protocolStack)) {
    console.log(`${layer.padEnd(12)}: ${protocols.join(", ")}`);
}


// ============================================================================
// ENCAPSULATION
// ============================================================================

section("ENCAPSULATION");

class ApplicationData {
    constructor(protocol, payload) {
        this.protocol = protocol;
        this.payload = Buffer.from(payload);
    }
}

class TransportSegment {
    constructor(protocol, sourcePort, destinationPort, payload) {
        this.protocol = protocol;
        this.sourcePort = sourcePort;
        this.destinationPort = destinationPort;
        this.payload = Buffer.from(payload);
    }
}

class IPPacket {
    constructor(sourceIp, destinationIp, protocol, payload) {
        if (!isValidIPv4(sourceIp) || !isValidIPv4(destinationIp)) {
            throw new Error("Invalid IP address.");
        }

        this.sourceIp = sourceIp;
        this.destinationIp = destinationIp;
        this.protocol = protocol;
        this.payload = Buffer.from(payload);
    }
}

class EthernetFrame {
    constructor(sourceMac, destinationMac, etherType, payload) {
        this.sourceMac = normalizeMac(sourceMac);
        this.destinationMac = normalizeMac(destinationMac);
        this.etherType = etherType;
        this.payload = Buffer.from(payload);
    }
}

const applicationData = new ApplicationData(
    "HTTP",
    "GET / HTTP/1.1\r\nHost: example.test\r\n\r\n"
);

const transportSegment = new TransportSegment(
    "TCP",
    53142,
    443,
    applicationData.payload
);

const ipPacket = new IPPacket(
    "192.168.1.25",
    "93.184.216.34",
    "TCP",
    transportSegment.payload
);

const ethernetFrame = new EthernetFrame(
    "00:11:22:33:44:55",
    "aa:bb:cc:dd:ee:ff",
    0x0800,
    ipPacket.payload
);

console.log("Application:", applicationData.protocol);
console.log(
    "Transport  :",
    transportSegment.protocol,
    transportSegment.sourcePort,
    "->",
    transportSegment.destinationPort
);
console.log(
    "IP         :",
    ipPacket.sourceIp,
    "->",
    ipPacket.destinationIp
);
console.log(
    "Ethernet   :",
    ethernetFrame.sourceMac,
    "->",
    ethernetFrame.destinationMac
);


// ============================================================================
// TCP FLAGS AND HANDSHAKE
// ============================================================================

section("TCP");

const TCP_FLAGS = Object.freeze({
    SYN: 0x02,
    ACK: 0x10,
    FIN: 0x01,
    RST: 0x04,
    PSH: 0x08
});

function flagsToText(flags) {
    const names = [];

    for (const [name, value] of Object.entries(TCP_FLAGS)) {
        if ((flags & value) !== 0) {
            names.push(name);
        }
    }

    return names.length ? names.join(", ") : "NONE";
}

class TCPSegment {
    constructor({
        sourcePort,
        destinationPort,
        sequenceNumber,
        acknowledgementNumber,
        flags,
        windowSize,
        payload = Buffer.alloc(0)
    }) {
        this.sourcePort = sourcePort;
        this.destinationPort = destinationPort;
        this.sequenceNumber = sequenceNumber;
        this.acknowledgementNumber = acknowledgementNumber;
        this.flags = flags;
        this.windowSize = windowSize;
        this.payload = Buffer.from(payload);
    }

    describe() {
        return [
            `${this.sourcePort} -> ${this.destinationPort}`,
            `seq=${this.sequenceNumber}`,
            `ack=${this.acknowledgementNumber}`,
            `flags=[${flagsToText(this.flags)}]`,
            `window=${this.windowSize}`,
            `payload=${this.payload.length} bytes`
        ].join(", ");
    }
}

function simulateTcpHandshake() {
    const clientPort = 53142;
    const serverPort = 443;

    const clientSequence = 1000;
    const serverSequence = 5000;

    return [
        new TCPSegment({
            sourcePort: clientPort,
            destinationPort: serverPort,
            sequenceNumber: clientSequence,
            acknowledgementNumber: 0,
            flags: TCP_FLAGS.SYN,
            windowSize: 64240
        }),

        new TCPSegment({
            sourcePort: serverPort,
            destinationPort: clientPort,
            sequenceNumber: serverSequence,
            acknowledgementNumber: clientSequence + 1,
            flags: TCP_FLAGS.SYN | TCP_FLAGS.ACK,
            windowSize: 65535
        }),

        new TCPSegment({
            sourcePort: clientPort,
            destinationPort: serverPort,
            sequenceNumber: clientSequence + 1,
            acknowledgementNumber: serverSequence + 1,
            flags: TCP_FLAGS.ACK,
            windowSize: 64240
        })
    ];
}

simulateTcpHandshake().forEach((segment, index) => {
    console.log(`${index + 1}. ${segment.describe()}`);
});


// ============================================================================
// UDP
// ============================================================================

section("UDP");

class UDPSegment {
    constructor(sourcePort, destinationPort, payload) {
        this.sourcePort = sourcePort;
        this.destinationPort = destinationPort;
        this.payload = Buffer.from(payload);
    }

    describe() {
        return (
            `${this.sourcePort} -> ${this.destinationPort}, ` +
            `payload=${this.payload.length} bytes`
        );
    }
}

const dnsDatagram = new UDPSegment(
    53000,
    53,
    "example.test"
);

console.log(dnsDatagram.describe());


// ============================================================================
// DNS
// ============================================================================

section("DNS");

const dnsRecords = new Map([
    ["example.test", {
        A: "192.0.2.10",
        AAAA: "2001:db8::10"
    }],
    ["api.example.test", {
        A: "192.0.2.20"
    }]
]);

function simulatedDnsLookup(hostname, recordType = "A") {
    const record = dnsRecords.get(hostname.toLowerCase());

    if (!record) {
        return null;
    }

    return record[recordType.toUpperCase()] ?? null;
}

for (const hostname of [
    "example.test",
    "api.example.test",
    "missing.test"
]) {
    console.log(
        hostname,
        "->",
        simulatedDnsLookup(hostname) ?? "NXDOMAIN / no record"
    );
}


// ============================================================================
// REAL DNS API DEMONSTRATION
// ============================================================================

section("NODE.JS DNS API");

dns.lookup("localhost", (error, address, family) => {
    if (error) {
        console.log("DNS lookup failed:", error.message);
        return;
    }

    console.log(
        `localhost -> ${address}, IPv${family}`
    );
});


// ============================================================================
// ARP CONCEPT
// ============================================================================

section("ARP");

const arpCache = new Map([
    ["192.168.1.1", "aa:aa:aa:aa:aa:01"],
    ["192.168.1.20", "aa:aa:aa:aa:aa:20"]
]);

function arpLookup(ip) {
    if (!isValidIPv4(ip)) {
        throw new Error("Invalid IPv4 address.");
    }

    return arpCache.get(ip) ?? null;
}

for (const ip of [
    "192.168.1.1",
    "192.168.1.20",
    "192.168.1.99"
]) {
    console.log(
        `${ip} -> ${arpLookup(ip) ?? "not in cache"}`
    );
}


// ============================================================================
// ICMP
// ============================================================================

section("ICMP");

const icmpTypes = new Map([
    [0, "Echo Reply"],
    [3, "Destination Unreachable"],
    [8, "Echo Request"],
    [11, "Time Exceeded"]
]);

class ICMPMessage {
    constructor(type, code, payload = "") {
        this.type = type;
        this.code = code;
        this.payload = Buffer.from(payload);
    }

    describe() {
        return icmpTypes.get(this.type) ?? "Unknown ICMP type";
    }
}

console.log(
    "Request:",
    new ICMPMessage(8, 0, "ping").describe()
);

console.log(
    "Reply  :",
    new ICMPMessage(0, 0, "ping").describe()
);


// ============================================================================
// ROUTING
// ============================================================================

section("ROUTING");

class Route {
    constructor(destinationNetwork, prefixLength, nextHop, interfaceName, metric = 0) {
        this.destinationNetwork = destinationNetwork;
        this.prefixLength = prefixLength;
        this.nextHop = nextHop;
        this.interfaceName = interfaceName;
        this.metric = metric;
    }

    matches(ip) {
        return networkAddress(ip, this.prefixLength) === this.destinationNetwork;
    }
}

class RoutingTable {
    constructor(routes) {
        this.routes = routes;
    }

    lookup(destination) {
        const matches = this.routes.filter(route => route.matches(destination));

        if (matches.length === 0) {
            return null;
        }

        return matches.sort((a, b) => {
            if (a.prefixLength !== b.prefixLength) {
                return b.prefixLength - a.prefixLength;
            }

            return a.metric - b.metric;
        })[0];
    }
}

const routingTable = new RoutingTable([
    new Route("192.168.1.0", 24, null, "LAN"),
    new Route("10.0.0.0", 8, "10.10.10.1", "WAN1"),
    new Route("0.0.0.0", 0, "192.168.1.1", "LAN")
]);

for (const destination of [
    "192.168.1.50",
    "10.20.30.40",
    "8.8.8.8"
]) {
    const route = routingTable.lookup(destination);

    console.log(
        `${destination.padEnd(16)} ->`,
        route
            ? `${route.destinationNetwork}/${route.prefixLength} ` +
              `via ${route.nextHop ?? "direct"} on ${route.interfaceName}`
            : "no route"
    );
}


// ============================================================================
// NETWORK DEVICES
// ============================================================================

section("NETWORK DEVICES");

const devices = {
    NIC: "Connects a host to the network.",
    Hub: "Repeats signals to multiple ports.",
    Switch: "Forwards Ethernet frames using MAC information.",
    Router: "Forwards IP packets between networks.",
    AccessPoint: "Provides wireless LAN connectivity.",
    Modem: "Provides access-network connectivity.",
    Firewall: "Filters traffic according to security policy.",
    LoadBalancer: "Distributes traffic among backend systems."
};

for (const [device, role] of Object.entries(devices)) {
    console.log(`${device.padEnd(16)}: ${role}`);
}


// ============================================================================
// NAT
// ============================================================================

section("NAT");

class NATEntry {
    constructor({
        internalIp,
        internalPort,
        externalIp,
        externalPort,
        destinationIp,
        destinationPort,
        protocol
    }) {
        this.internalIp = internalIp;
        this.internalPort = internalPort;
        this.externalIp = externalIp;
        this.externalPort = externalPort;
        this.destinationIp = destinationIp;
        this.destinationPort = destinationPort;
        this.protocol = protocol.toUpperCase();
    }
}

const natEntry = new NATEntry({
    internalIp: "192.168.1.25",
    internalPort: 53142,
    externalIp: "203.0.113.20",
    externalPort: 42001,
    destinationIp: "93.184.216.34",
    destinationPort: 443,
    protocol: "TCP"
});

console.log(
    "Internal   :",
    `${natEntry.internalIp}:${natEntry.internalPort}`
);

console.log(
    "Translated :",
    `${natEntry.externalIp}:${natEntry.externalPort}`
);

console.log(
    "Destination:",
    `${natEntry.destinationIp}:${natEntry.destinationPort}`
);


// ============================================================================
// FIREWALL
// ============================================================================

section("FIREWALL");

class FirewallRule {
    constructor({
        sourceNetwork,
        prefixLength,
        destinationPort = null,
        protocol = null,
        action,
        description
    }) {
        this.sourceNetwork = sourceNetwork;
        this.prefixLength = prefixLength;
        this.destinationPort = destinationPort;
        this.protocol = protocol?.toUpperCase() ?? null;
        this.action = action;
        this.description = description;
    }

    matches(sourceIp, destinationPort, protocol) {
        if (networkAddress(sourceIp, this.prefixLength) !== this.sourceNetwork) {
            return false;
        }

        if (
            this.destinationPort !== null &&
            this.destinationPort !== destinationPort
        ) {
            return false;
        }

        if (
            this.protocol !== null &&
            this.protocol !== protocol.toUpperCase()
        ) {
            return false;
        }

        return true;
    }
}

class SimpleFirewall {
    constructor(rules) {
        this.rules = rules;
    }

    evaluate(sourceIp, destinationPort, protocol) {
        for (const rule of this.rules) {
            if (rule.matches(sourceIp, destinationPort, protocol)) {
                return {
                    action: rule.action,
                    reason: rule.description
                };
            }
        }

        return {
            action: "DENY",
            reason: "Implicit deny"
        };
    }
}

const firewall = new SimpleFirewall([
    new FirewallRule({
        sourceNetwork: "192.168.1.0",
        prefixLength: 24,
        destinationPort: 443,
        protocol: "TCP",
        action: "ALLOW",
        description: "Allow HTTPS from LAN"
    }),

    new FirewallRule({
        sourceNetwork: "192.168.1.0",
        prefixLength: 24,
        destinationPort: 22,
        protocol: "TCP",
        action: "DENY",
        description: "Block SSH from LAN"
    })
]);

for (const test of [
    ["192.168.1.25", 443, "TCP"],
    ["192.168.1.25", 22, "TCP"],
    ["192.168.1.25", 53, "UDP"]
]) {
    const result = firewall.evaluate(...test);

    console.log(
        `${test[0]} -> ${test[2]}/${test[1]}: ` +
        `${result.action} (${result.reason})`
    );
}


// ============================================================================
// PACKET MODEL
// ============================================================================

section("PACKET MODEL");

class Packet {
    constructor({
        number,
        timestamp,
        sourceMac,
        destinationMac,
        sourceIp,
        destinationIp,
        transportProtocol,
        sourcePort = null,
        destinationPort = null,
        flags = null,
        payload = "",
        applicationProtocol = null,
        info = ""
    }) {
        this.number = number;
        this.timestamp = timestamp;
        this.sourceMac = normalizeMac(sourceMac);
        this.destinationMac = normalizeMac(destinationMac);
        this.sourceIp = sourceIp;
        this.destinationIp = destinationIp;
        this.transportProtocol = transportProtocol;
        this.sourcePort = sourcePort;
        this.destinationPort = destinationPort;
        this.flags = flags;
        this.payload = Buffer.from(payload);
        this.applicationProtocol = applicationProtocol;
        this.info = info;
    }

    get length() {
        return this.payload.length;
    }

    summary() {
        const endpoints = this.sourcePort !== null
            ? `${this.sourceIp}:${this.sourcePort} -> ` +
              `${this.destinationIp}:${this.destinationPort}`
            : `${this.sourceIp} -> ${this.destinationIp}`;

        const flags = this.flags !== null
            ? ` [${flagsToText(this.flags)}]`
            : "";

        return [
            String(this.number).padStart(3),
            this.transportProtocol.padEnd(5),
            endpoints.padEnd(45),
            (this.applicationProtocol ?? "-").padEnd(8),
            flags.padEnd(20),
            `len=${String(this.length).padStart(4)}`,
            this.info
        ].join(" ");
    }
}

const baseTime = Date.now() / 1000;

const packets = [
    new Packet({
        number: 1,
        timestamp: baseTime,
        sourceMac: "00:11:22:33:44:55",
        destinationMac: "aa:bb:cc:dd:ee:ff",
        sourceIp: "192.168.1.25",
        destinationIp: "93.184.216.34",
        transportProtocol: "TCP",
        sourcePort: 53142,
        destinationPort: 443,
        flags: TCP_FLAGS.SYN,
        info: "SYN"
    }),

    new Packet({
        number: 2,
        timestamp: baseTime + 0.001,
        sourceMac: "aa:bb:cc:dd:ee:ff",
        destinationMac: "00:11:22:33:44:55",
        sourceIp: "93.184.216.34",
        destinationIp: "192.168.1.25",
        transportProtocol: "TCP",
        sourcePort: 443,
        destinationPort: 53142,
        flags: TCP_FLAGS.SYN | TCP_FLAGS.ACK,
        info: "SYN, ACK"
    }),

    new Packet({
        number: 3,
        timestamp: baseTime + 0.002,
        sourceMac: "00:11:22:33:44:55",
        destinationMac: "aa:bb:cc:dd:ee:ff",
        sourceIp: "192.168.1.25",
        destinationIp: "93.184.216.34",
        transportProtocol: "TCP",
        sourcePort: 53142,
        destinationPort: 443,
        flags: TCP_FLAGS.ACK,
        info: "ACK"
    }),

    new Packet({
        number: 4,
        timestamp: baseTime + 0.005,
        sourceMac: "00:11:22:33:44:55",
        destinationMac: "aa:bb:cc:dd:ee:ff",
        sourceIp: "192.168.1.25",
        destinationIp: "93.184.216.34",
        transportProtocol: "TCP",
        sourcePort: 53142,
        destinationPort: 443,
        flags: TCP_FLAGS.ACK | TCP_FLAGS.PSH,
        payload: "GET / HTTP/1.1\r\nHost: example.test\r\n\r\n",
        applicationProtocol: "HTTP",
        info: "HTTP GET /"
    }),

    new Packet({
        number: 5,
        timestamp: baseTime + 0.030,
        sourceMac: "00:11:22:33:44:55",
        destinationMac: "aa:bb:cc:dd:ee:ff",
        sourceIp: "192.168.1.25",
        destinationIp: "8.8.8.8",
        transportProtocol: "UDP",
        sourcePort: 53000,
        destinationPort: 53,
        payload: "example.test",
        applicationProtocol: "DNS",
        info: "DNS query"
    }),

    new Packet({
        number: 6,
        timestamp: baseTime + 0.040,
        sourceMac: "00:11:22:33:44:55",
        destinationMac: "aa:bb:cc:dd:ee:ff",
        sourceIp: "192.168.1.25",
        destinationIp: "1.1.1.1",
        transportProtocol: "ICMP",
        payload: "ping",
        applicationProtocol: "ICMP",
        info: "Echo request"
    })
];

console.log(
    "No. Proto Source/Destination                                " +
    "App      Flags                Length Info"
);

console.log("-".repeat(120));

for (const packet of packets) {
    console.log(packet.summary());
}


// ============================================================================
// PACKET FILTERING
// ============================================================================

section("PACKET FILTERING");

function filterPackets(packetList, {
    protocol = null,
    source = null,
    destination = null,
    port = null,
    application = null
} = {}) {
    return packetList.filter(packet => {
        if (
            protocol !== null &&
            packet.transportProtocol.toUpperCase() !== protocol.toUpperCase()
        ) {
            return false;
        }

        if (source !== null && packet.sourceIp !== source) {
            return false;
        }

        if (destination !== null && packet.destinationIp !== destination) {
            return false;
        }

        if (
            port !== null &&
            packet.sourcePort !== port &&
            packet.destinationPort !== port
        ) {
            return false;
        }

        if (
            application !== null &&
            packet.applicationProtocol?.toUpperCase() !==
            application.toUpperCase()
        ) {
            return false;
        }

        return true;
    });
}

for (const packet of filterPackets(packets, { protocol: "TCP" })) {
    console.log(packet.summary());
}

console.log("\nPackets using port 443:");

for (const packet of filterPackets(packets, { port: 443 })) {
    console.log(packet.summary());
}

console.log("\nDNS packets:");

for (const packet of filterPackets(packets, { application: "DNS" })) {
    console.log(packet.summary());
}


// ============================================================================
// WIRESHARK CONCEPTS
// ============================================================================

section("WIRESHARK DISPLAY-FILTER CONCEPTS");

const filters = {
    "tcp": "Show TCP packets.",
    "udp": "Show UDP packets.",
    "dns": "Show DNS packets.",
    "http": "Show HTTP packets.",
    "icmp": "Show ICMP packets.",
    "ip.addr == 192.168.1.25":
        "Match packets with this address as either endpoint.",
    "ip.src == 192.168.1.25":
        "Match packets originating from this address.",
    "ip.dst == 8.8.8.8":
        "Match packets sent to this address.",
    "tcp.port == 443":
        "Match TCP packets using port 443.",
    "tcp.flags.syn == 1":
        "Match TCP packets with SYN set.",
    "tcp.flags.reset == 1":
        "Match TCP reset packets.",
    "tcp.stream == 0":
        "Select packets belonging to one TCP conversation."
};

for (const [expression, explanation] of Object.entries(filters)) {
    console.log(`${expression.padEnd(38)} -> ${explanation}`);
}

console.log(`
Capture filters and display filters serve different purposes.

A capture filter restricts traffic collected by the capture process.

A display filter restricts which already captured packets are shown.

A display filter can therefore be changed repeatedly while preserving
the original capture data.
`);


// ============================================================================
// TCP STREAM GROUPING
// ============================================================================

section("TCP STREAM GROUPING");

function streamKey(packet) {
    if (
        packet.sourcePort === null ||
        packet.destinationPort === null
    ) {
        return null;
    }

    const endpointA =
        `${packet.sourceIp}:${packet.sourcePort}`;

    const endpointB =
        `${packet.destinationIp}:${packet.destinationPort}`;

    return [endpointA, endpointB].sort().join(" <-> ");
}

const streams = new Map();

for (const packet of packets) {
    if (packet.transportProtocol !== "TCP") {
        continue;
    }

    const key = streamKey(packet);

    if (!streams.has(key)) {
        streams.set(key, []);
    }

    streams.get(key).push(packet);
}

for (const [key, streamPackets] of streams) {
    console.log("\nStream:", key);

    for (const packet of streamPackets) {
        console.log(
            `  #${packet.number}: ${packet.info}`
        );
    }
}


// ============================================================================
// PACKET STATISTICS
// ============================================================================

section("PACKET STATISTICS");

function protocolCounts(packetList) {
    const counts = new Map();

    for (const packet of packetList) {
        counts.set(
            packet.transportProtocol,
            (counts.get(packet.transportProtocol) ?? 0) + 1
        );
    }

    return counts;
}

for (const [protocol, count] of protocolCounts(packets)) {
    console.log(`${protocol}: ${count}`);
}

function topTalkers(packetList, limit = 5) {
    const counts = new Map();

    for (const packet of packetList) {
        counts.set(
            packet.sourceIp,
            (counts.get(packet.sourceIp) ?? 0) + packet.length
        );

        counts.set(
            packet.destinationIp,
            (counts.get(packet.destinationIp) ?? 0) + packet.length
        );
    }

    return [...counts.entries()]
        .sort((a, b) => b[1] - a[1])
        .slice(0, limit);
}

console.log("\nTop observed addresses by payload bytes:");

for (const [address, bytes] of topTalkers(packets)) {
    console.log(`${address.padEnd(16)} ${bytes} bytes`);
}


// ============================================================================
// LATENCY
// ============================================================================

section("TIMING AND LATENCY");

const orderedPackets = [...packets]
    .sort((a, b) => a.timestamp - b.timestamp);

const delays = [];

for (let index = 1; index < orderedPackets.length; index++) {
    delays.push(
        orderedPackets[index].timestamp -
        orderedPackets[index - 1].timestamp
    );
}

console.log("Inter-packet delays:");

for (const delay of delays) {
    console.log(`${(delay * 1000).toFixed(3)} ms`);
}

if (delays.length > 0) {
    const average =
        delays.reduce((sum, value) => sum + value, 0) /
        delays.length;

    console.log("Average:", `${(average * 1000).toFixed(3)} ms`);
}


// ============================================================================
// THROUGHPUT
// ============================================================================

section("THROUGHPUT");

function calculateThroughput(bytes, seconds) {
    if (seconds <= 0) {
        throw new Error("Duration must be greater than zero.");
    }

    return {
        bytesPerSecond: bytes / seconds,
        bitsPerSecond: (bytes * 8) / seconds,
        megabitsPerSecond: (bytes * 8) / seconds / 1_000_000
    };
}

const throughput = calculateThroughput(
    125_000_000,
    10
);

console.log(
    "Bytes/s:",
    throughput.bytesPerSecond.toFixed(2)
);

console.log(
    "Bits/s:",
    throughput.bitsPerSecond.toFixed(2)
);

console.log(
    "Mbps:",
    throughput.megabitsPerSecond.toFixed(2)
);


// ============================================================================
// CHECKSUM
// ============================================================================

section("INTERNET CHECKSUM");

function internetChecksum(buffer) {
    let data = Buffer.from(buffer);

    if (data.length % 2 !== 0) {
        data = Buffer.concat([
            data,
            Buffer.from([0])
        ]);
    }

    let total = 0;

    for (let index = 0; index < data.length; index += 2) {
        const word =
            (data[index] << 8) |
            data[index + 1];

        total += word;
        total = (total & 0xffff) + (total >>> 16);
    }

    return (~total) & 0xffff;
}

for (const value of [
    "",
    "hello",
    "network packet"
]) {
    const checksum = internetChecksum(
        Buffer.from(value)
    );

    console.log(
        JSON.stringify(value),
        `-> 0x${checksum.toString(16).padStart(4, "0")}`
    );
}


// ============================================================================
// HTTP
// ============================================================================

section("HTTP");

const httpRequest =
    "GET /index.html HTTP/1.1\r\n" +
    "Host: example.test\r\n" +
    "Accept: text/html\r\n" +
    "Connection: close\r\n" +
    "\r\n";

console.log(httpRequest);

function parseHttpRequest(request) {
    const lines = request.split("\r\n");

    const requestLine = lines.shift();
    const headers = {};

    for (const line of lines) {
        if (line === "") {
            break;
        }

        const separator = line.indexOf(":");

        if (separator === -1) {
            continue;
        }

        const name = line.slice(0, separator).trim();
        const value = line.slice(separator + 1).trim();

        headers[name.toLowerCase()] = value;
    }

    const [method, path, version] = requestLine.split(" ");

    return {
        method,
        path,
        version,
        headers
    };
}

console.log(
    "Parsed HTTP request:",
    parseHttpRequest(httpRequest)
);


// ============================================================================
// HTTPS
// ============================================================================

section("HTTPS");

console.log(`
HTTPS protects HTTP traffic with TLS.

A packet analyzer can still observe important metadata such as:

  - Source and destination IP addresses
  - Transport protocol
  - Ports
  - Packet lengths
  - Timing
  - Connection setup

The encrypted application payload normally cannot be interpreted as
ordinary plaintext simply by looking at the packets.

Modern HTTP/3 commonly uses QUIC over UDP, which changes the transport
behavior visible to a packet analyzer.
`);


// ============================================================================
// ROUTING CASE STUDY
// ============================================================================

section("ROUTING CASE STUDY");

const destinations = [
    "192.168.1.100",
    "10.1.2.3",
    "8.8.8.8",
    "192.168.2.10"
];

for (const destination of destinations) {
    const route = routingTable.lookup(destination);

    console.log(
        `${destination.padEnd(16)} ->`,
        route
            ? `${route.destinationNetwork}/${route.prefixLength}, ` +
              `interface=${route.interfaceName}, ` +
              `next-hop=${route.nextHop ?? "direct"}`
            : "NO ROUTE"
    );
}


// ============================================================================
// NODE TCP SOCKET API
// ============================================================================

section("NODE.JS TCP SOCKET API");

const socket = new net.Socket();

console.log("Socket created.");
console.log("Readable before connection:", socket.readable);
console.log("Writable before connection:", socket.writable);

socket.destroy();

console.log("Socket destroyed safely.");


// ============================================================================
// CRYPTOGRAPHIC HASH AND NETWORK INTEGRITY CONCEPT
// ============================================================================

section("HASHING AND INTEGRITY CONCEPT");

const samplePayload = Buffer.from(
    "network payload"
);

const digest = crypto
    .createHash("sha256")
    .update(samplePayload)
    .digest("hex");

console.log("Payload:", samplePayload.toString());
console.log("SHA-256:", digest);

console.log(`
A cryptographic hash is not a replacement for every network checksum.

Checksums are often designed for efficient error detection.

Cryptographic hashes provide stronger integrity properties and are
commonly used as part of security mechanisms.
`);


// ============================================================================
// MTU
// ============================================================================

section("MTU");

function requiresOversizeHandling(payloadSize, mtu = 1500) {
    if (payloadSize < 0) {
        throw new Error("Payload size cannot be negative.");
    }

    const ipv4HeaderSize = 20;

    return payloadSize + ipv4HeaderSize > mtu;
}

for (const payloadSize of [100, 1400, 1480, 1500, 2000]) {
    console.log(
        `Payload=${String(payloadSize).padStart(4)} ` +
        `MTU=1500 ` +
        `oversize=${requiresOversizeHandling(payloadSize)}`
    );
}


// ============================================================================
// PACKET LOSS
// ============================================================================

section("PACKET LOSS SIMULATION");

function simulatePacketLoss(packetCount, lossProbability, seed = 7) {
    if (
        !Number.isInteger(packetCount) ||
        packetCount < 0
    ) {
        throw new Error("Packet count must be non-negative.");
    }

    if (lossProbability < 0 || lossProbability > 1) {
        throw new Error("Loss probability must be from 0 through 1.");
    }

    /*
     * JavaScript Math.random() is intentionally not seeded.
     * A deterministic linear congruential generator is used so that
     * this teaching example produces repeatable output.
     */
    let state = seed >>> 0;

    function random() {
        state =
            (1664525 * state + 1013904223) >>> 0;

        return state / 0x100000000;
    }

    const delivered = [];
    const lost = [];

    for (let sequence = 1; sequence <= packetCount; sequence++) {
        if (random() < lossProbability) {
            lost.push(sequence);
        } else {
            delivered.push(sequence);
        }
    }

    return {
        delivered,
        lost
    };
}

const lossResult = simulatePacketLoss(20, 0.2);

console.log("Delivered:", lossResult.delivered);
console.log("Lost     :", lossResult.lost);
console.log(
    "Delivery ratio:",
    `${(lossResult.delivered.length / 20 * 100).toFixed(1)}%`
);


// ============================================================================
// TCP STATE MACHINE
// ============================================================================

section("TCP STATE MACHINE");

const tcpStates = [
    "CLOSED",
    "LISTEN",
    "SYN-SENT",
    "SYN-RECEIVED",
    "ESTABLISHED",
    "FIN-WAIT-1",
    "FIN-WAIT-2",
    "CLOSE-WAIT",
    "LAST-ACK",
    "TIME-WAIT"
];

tcpStates.forEach((state, index) => {
    console.log(`${String(index + 1).padStart(2)}. ${state}`);
});


// ============================================================================
// TROUBLESHOOTING
// ============================================================================

section("NETWORK TROUBLESHOOTING");

const troubleshooting = [
    "Check physical connectivity or wireless association.",
    "Check IP address and subnet configuration.",
    "Check the default gateway.",
    "Test local network reachability.",
    "Check DNS resolution.",
    "Inspect the route to the destination.",
    "Check TCP/UDP port reachability.",
    "Inspect application protocol behavior.",
    "Check firewalls and access-control rules.",
    "Compare packet timing, retransmissions and resets."
];

troubleshooting.forEach((item, index) => {
    console.log(`${index + 1}. ${item}`);
});


// ============================================================================
// SECURITY
// ============================================================================

section("NETWORK SECURITY");

console.log(`
Packet captures may contain sensitive information.

Potentially exposed information includes:

  - IP addresses
  - Hostnames
  - Application metadata
  - Cookies
  - Authentication material
  - Unencrypted application content
  - Internal infrastructure details

Capture files should therefore be protected appropriately.

Encryption reduces the visibility of application payloads, but it does
not make all network metadata invisible.
`);


// ============================================================================
// WIRESHARK ANALYSIS CHECKLIST
// ============================================================================

section("WIRESHARK ANALYSIS CHECKLIST");

const checklist = [
    "Define the networking question being investigated.",
    "Identify relevant hosts.",
    "Identify the relevant time interval.",
    "Check packet timestamps and lengths.",
    "Inspect link-layer addresses where relevant.",
    "Inspect source and destination IP addresses.",
    "Identify TCP or UDP ports.",
    "Inspect protocol flags.",
    "Follow relevant TCP streams.",
    "Inspect DNS queries and responses.",
    "Look for retransmissions, resets and duplicate acknowledgements.",
    "Compare request and response timing.",
    "Determine whether encryption limits payload visibility.",
    "Correlate packet observations with application behavior."
];

checklist.forEach((item, index) => {
    console.log(`${String(index + 1).padStart(2)}. ${item}`);
});


// ============================================================================
// SELF-TESTS
// ============================================================================

section("SELF-TESTS");

function runTests() {
    console.assert(
        normalizeMac("AABBCCDDEEFF") ===
        "aa:bb:cc:dd:ee:ff"
    );

    console.assert(isValidIPv4("127.0.0.1"));
    console.assert(!isValidIPv4("300.1.1.1"));

    console.assert(
        networkAddress("192.168.1.25", 24) ===
        "192.168.1.0"
    );

    console.assert(
        broadcastAddress("192.168.1.25", 24) ===
        "192.168.1.255"
    );

    console.assert(describePort(443) === "HTTPS");

    const handshake = simulateTcpHandshake();

    console.assert(
        (handshake[0].flags & TCP_FLAGS.SYN) !== 0
    );

    console.assert(
        (handshake[1].flags & TCP_FLAGS.SYN) !== 0
    );

    console.assert(
        (handshake[1].flags & TCP_FLAGS.ACK) !== 0
    );

    console.assert(
        (handshake[2].flags & TCP_FLAGS.ACK) !== 0
    );

    console.assert(
        simulatedDnsLookup("example.test") ===
        "192.0.2.10"
    );

    console.assert(
        firewall.evaluate(
            "192.168.1.25",
            443,
            "TCP"
        ).action === "ALLOW"
    );

    console.assert(
        firewall.evaluate(
            "192.168.1.25",
            22,
            "TCP"
        ).action === "DENY"
    );

    console.assert(
        filterPackets(packets, {
            application: "DNS"
        }).length === 1
    );

    console.log("All self-tests passed.");
}

runTests();


// ============================================================================
// QUICK REFERENCE
// ============================================================================

section("QUICK REFERENCE");

const quickReference = [
    ["Ethernet", "Link", "Frames and MAC addresses"],
    ["ARP", "Link", "IPv4-to-MAC resolution"],
    ["IP", "Internet", "Logical addressing and routing"],
    ["ICMP", "Internet", "Control and diagnostic messages"],
    ["TCP", "Transport", "Reliable ordered byte stream"],
    ["UDP", "Transport", "Connectionless datagrams"],
    ["DNS", "Application", "Name resolution"],
    ["DHCP", "Application", "Automatic network configuration"],
    ["HTTP", "Application", "Web communication"],
    ["HTTPS", "Application/Security", "TLS-protected HTTP"],
    ["Wireshark", "Analysis", "Packet capture and inspection"]
];

for (const [technology, layer, purpose] of quickReference) {
    console.log(
        `${technology.padEnd(12)} | ` +
        `${layer.padEnd(18)} | ${purpose}`
    );
}

console.log(`
Core analytical model:

Application
    ↓
Transport
    ↓
Internet
    ↓
Link
    ↓
Physical transmission

Packet analysis becomes useful when individual fields are connected to
the behavior of the complete communication.
`);
