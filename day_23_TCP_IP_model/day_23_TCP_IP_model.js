/*
 * TCP/IP MODEL
 * ============
 *
 * A self-contained JavaScript study program covering:
 *
 * - Network Access layer
 * - Internet layer
 * - Transport layer
 * - Application layer
 * - Protocol mapping
 * - Encapsulation and decapsulation
 * - IPv4 and IPv6 addressing
 * - Subnetting
 * - Routing
 * - TCP and UDP
 * - TCP connection establishment
 * - Ports
 * - DNS
 * - HTTP
 * - NAT
 * - MTU
 * - Checksums
 * - Error handling
 * - Security
 * - Performance
 *
 * Run with:
 *     node tcp-ip-model.js
 *
 * The examples are educational models. Some mechanisms are simplified
 * versions of what operating-system network stacks implement.
 */

"use strict";

const crypto = require("crypto");
const net = require("net");

// ---------------------------------------------------------------------------
// 1. TCP/IP MODEL
// ---------------------------------------------------------------------------

const Layers = Object.freeze({
    NETWORK_ACCESS: "Network Access",
    INTERNET: "Internet",
    TRANSPORT: "Transport",
    APPLICATION: "Application"
});

const protocolMapping = {
    Ethernet: Layers.NETWORK_ACCESS,
    WiFi: Layers.NETWORK_ACCESS,
    ARP: Layers.NETWORK_ACCESS,

    IPv4: Layers.INTERNET,
    IPv6: Layers.INTERNET,
    ICMP: Layers.INTERNET,

    TCP: Layers.TRANSPORT,
    UDP: Layers.TRANSPORT,

    DNS: Layers.APPLICATION,
    HTTP: Layers.APPLICATION,
    HTTPS: Layers.APPLICATION,
    DHCP: Layers.APPLICATION,
    SSH: Layers.APPLICATION
};

function showModel() {
    console.log("\nTCP/IP MODEL");
    console.log("-".repeat(72));

    console.log("1. Network Access");
    console.log(
        "   Local delivery over technologies such as Ethernet and Wi-Fi."
    );

    console.log("2. Internet");
    console.log(
        "   Logical addressing and routing using IPv4, IPv6 and related protocols."
    );

    console.log("3. Transport");
    console.log(
        "   Process-to-process communication using TCP and UDP."
    );

    console.log("4. Application");
    console.log(
        "   Services such as DNS, HTTP, HTTPS, DHCP and SSH."
    );

    console.log("\nProtocol mapping:");

    for (const [protocol, layer] of Object.entries(protocolMapping)) {
        console.log(`  ${protocol.padEnd(10)} -> ${layer}`);
    }
}

// ---------------------------------------------------------------------------
// 2. ENCAPSULATION
// ---------------------------------------------------------------------------

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
        this.payload = payload;
    }
}

class IPPacket {
    constructor(protocol, sourceIP, destinationIP, payload, ttl = 64) {
        this.protocol = protocol;
        this.sourceIP = sourceIP;
        this.destinationIP = destinationIP;
        this.payload = payload;
        this.ttl = ttl;
    }
}

class NetworkFrame {
    constructor(technology, sourceMAC, destinationMAC, payload) {
        this.technology = technology;
        this.sourceMAC = sourceMAC;
        this.destinationMAC = destinationMAC;
        this.payload = payload;
    }
}

function demonstrateEncapsulation() {
    console.log("\nENCAPSULATION");
    console.log("-".repeat(72));

    const application = new ApplicationData(
        "HTTP",
        "GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"
    );

    const transport = new TransportSegment(
        "TCP",
        51500,
        80,
        application.payload
    );

    const packet = new IPPacket(
        "IPv4/TCP",
        "192.168.1.10",
        "93.184.216.34",
        transport
    );

    const frame = new NetworkFrame(
        "Ethernet",
        "02:00:00:00:00:10",
        "02:00:00:00:00:01",
        packet
    );

    console.log(
        `Application: ${application.protocol}, ` +
        `${application.payload.length} bytes`
    );

    console.log(
        `Transport: ${transport.protocol}, ` +
        `${transport.sourcePort} -> ${transport.destinationPort}`
    );

    console.log(
        `Internet: ${packet.sourceIP} -> ${packet.destinationIP}, ` +
        `TTL=${packet.ttl}`
    );

    console.log(
        `Network Access: ${frame.technology}, ` +
        `${frame.sourceMAC} -> ${frame.destinationMAC}`
    );

    console.log(
        "\nDecapsulation removes these headers in the reverse direction."
    );
}

// ---------------------------------------------------------------------------
// 3. MAC ADDRESS VALIDATION
// ---------------------------------------------------------------------------

function normalizeMAC(mac) {
    const normalized = mac.replace(/-/g, ":").toLowerCase();
    const parts = normalized.split(":");

    if (
        parts.length !== 6 ||
        parts.some(part => !/^[0-9a-f]{2}$/.test(part))
    ) {
        throw new Error(`Invalid MAC address: ${mac}`);
    }

    return parts.join(":");
}

function demonstrateMAC() {
    console.log("\nMAC ADDRESSING");
    console.log("-".repeat(72));

    for (const mac of [
        "00:1A:2B:3C:4D:5E",
        "AA-BB-CC-DD-EE-FF"
    ]) {
        console.log(`${mac} -> ${normalizeMAC(mac)}`);
    }

    try {
        normalizeMAC("invalid");
    } catch (error) {
        console.log(`Rejected invalid address: ${error.message}`);
    }
}

// ---------------------------------------------------------------------------
// 4. IPV4 VALIDATION
// ---------------------------------------------------------------------------

function isValidIPv4(address) {
    const parts = address.split(".");

    if (parts.length !== 4) {
        return false;
    }

    return parts.every(part => {
        if (!/^\d+$/.test(part)) {
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
        .reduce(
            (value, octet) => ((value << 8) | Number(octet)) >>> 0,
            0
        );
}

function demonstrateIPv4() {
    console.log("\nIPv4 ADDRESSING");
    console.log("-".repeat(72));

    for (const address of [
        "127.0.0.1",
        "192.168.1.10",
        "10.20.30.40",
        "8.8.8.8"
    ]) {
        console.log(
            `${address}: valid=${isValidIPv4(address)}, ` +
            `integer=${ipv4ToInteger(address)}`
        );
    }

    for (const address of [
        "999.1.1.1",
        "192.168.1.999",
        "hello"
    ]) {
        console.log(`${address}: valid=${isValidIPv4(address)}`);
    }
}

// ---------------------------------------------------------------------------
// 5. IPV6 BASIC RECOGNITION
// ---------------------------------------------------------------------------

function looksLikeIPv6(address) {
    /*
     * This intentionally performs a basic structural check rather than
     * implementing the complete IPv6 grammar. Production validation should
     * use a well-tested networking library.
     */
    return (
        address.includes(":") &&
        address.split(":").length >= 3 &&
        /^[0-9a-fA-F:]+$/.test(address)
    );
}

function demonstrateIPv6() {
    console.log("\nIPv6");
    console.log("-".repeat(72));

    for (const address of [
        "::1",
        "2001:db8::1",
        "fe80::1234"
    ]) {
        console.log(`${address}: IPv6-like=${looksLikeIPv6(address)}`);
    }
}

// ---------------------------------------------------------------------------
// 6. SUBNET CALCULATIONS
// ---------------------------------------------------------------------------

function prefixMask(prefix) {
    if (!Number.isInteger(prefix) || prefix < 0 || prefix > 32) {
        throw new Error("IPv4 prefix must be between 0 and 32");
    }

    if (prefix === 0) {
        return 0;
    }

    return (0xffffffff << (32 - prefix)) >>> 0;
}

function integerToIPv4(value) {
    return [
        (value >>> 24) & 255,
        (value >>> 16) & 255,
        (value >>> 8) & 255,
        value & 255
    ].join(".");
}

function subnetInformation(address, prefix) {
    const ip = ipv4ToInteger(address);
    const mask = prefixMask(prefix);
    const network = ip & mask;
    const broadcast = network | (~mask >>> 0);

    let usableHosts;

    if (prefix <= 30) {
        usableHosts = Math.pow(2, 32 - prefix) - 2;
    } else {
        usableHosts = Math.pow(2, 32 - prefix);
    }

    return {
        network: integerToIPv4(network),
        broadcast: integerToIPv4(broadcast),
        mask: integerToIPv4(mask),
        usableHosts
    };
}

function demonstrateSubnetting() {
    console.log("\nSUBNETTING");
    console.log("-".repeat(72));

    for (const [address, prefix] of [
        ["192.168.1.10", 24],
        ["192.168.1.70", 26],
        ["10.20.30.4", 30]
    ]) {
        const result = subnetInformation(address, prefix);

        console.log(
            `${address}/${prefix}: ` +
            `network=${result.network}, ` +
            `broadcast=${result.broadcast}, ` +
            `mask=${result.mask}, ` +
            `hosts=${result.usableHosts}`
        );
    }
}

// ---------------------------------------------------------------------------
// 7. ROUTING
// ---------------------------------------------------------------------------

class Route {
    constructor(network, prefix, nextHop, interfaceName) {
        this.network = network;
        this.prefix = prefix;
        this.nextHop = nextHop;
        this.interfaceName = interfaceName;
    }

    contains(address) {
        const target = ipv4ToInteger(address);
        const networkValue = ipv4ToInteger(this.network);
        const mask = prefixMask(this.prefix);

        return (target & mask) === (networkValue & mask);
    }
}

class RoutingTable {
    constructor() {
        this.routes = [];
    }

    addRoute(network, prefix, nextHop, interfaceName) {
        this.routes.push(
            new Route(network, prefix, nextHop, interfaceName)
        );
    }

    lookup(destination) {
        const matches = this.routes.filter(route =>
            route.contains(destination)
        );

        if (matches.length === 0) {
            return null;
        }

        return matches.reduce((best, route) =>
            route.prefix > best.prefix ? route : best
        );
    }
}

function demonstrateRouting() {
    console.log("\nROUTING AND LONGEST PREFIX MATCH");
    console.log("-".repeat(72));

    const table = new RoutingTable();

    table.addRoute("0.0.0.0", 0, "192.168.1.1", "eth0");
    table.addRoute("10.0.0.0", 8, "192.168.1.254", "eth1");
    table.addRoute("10.10.0.0", 16, "192.168.1.253", "eth2");
    table.addRoute("10.10.20.0", 24, "192.168.1.252", "eth3");

    for (const destination of [
        "8.8.8.8",
        "10.20.1.5",
        "10.10.5.10",
        "10.10.20.42"
    ]) {
        const route = table.lookup(destination);

        if (!route) {
            console.log(`${destination}: no route`);
        } else {
            console.log(
                `${destination}: /${route.prefix} -> ` +
                `${route.nextHop} via ${route.interfaceName}`
            );
        }
    }
}

// ---------------------------------------------------------------------------
// 8. INTERNET CHECKSUM
// ---------------------------------------------------------------------------

function internetChecksum(buffer) {
    let data = Buffer.from(buffer);

    if (data.length % 2 !== 0) {
        data = Buffer.concat([data, Buffer.from([0])]);
    }

    let sum = 0;

    for (let index = 0; index < data.length; index += 2) {
        const word = (data[index] << 8) | data[index + 1];

        sum += word;

        while (sum > 0xffff) {
            sum = (sum & 0xffff) + (sum >>> 16);
        }
    }

    return (~sum) & 0xffff;
}

function demonstrateChecksum() {
    console.log("\nINTERNET CHECKSUM");
    console.log("-".repeat(72));

    const data = Buffer.from("TCP/IP checksum demonstration");
    const checksum = internetChecksum(data);

    console.log(`Data: ${data.toString()}`);
    console.log(`Checksum: 0x${checksum.toString(16).padStart(4, "0")}`);
}

// ---------------------------------------------------------------------------
// 9. UDP DATAGRAM
// ---------------------------------------------------------------------------

class UDPDatagram {
    constructor(sourcePort, destinationPort, payload) {
        if (
            !Number.isInteger(sourcePort) ||
            sourcePort < 0 ||
            sourcePort > 65535
        ) {
            throw new Error("Invalid source port");
        }

        if (
            !Number.isInteger(destinationPort) ||
            destinationPort < 0 ||
            destinationPort > 65535
        ) {
            throw new Error("Invalid destination port");
        }

        this.sourcePort = sourcePort;
        this.destinationPort = destinationPort;
        this.payload = Buffer.from(payload);
    }

    encode() {
        const length = 8 + this.payload.length;

        const header = Buffer.alloc(8);

        header.writeUInt16BE(this.sourcePort, 0);
        header.writeUInt16BE(this.destinationPort, 2);
        header.writeUInt16BE(length, 4);

        // This educational example leaves the UDP checksum as zero.
        header.writeUInt16BE(0, 6);

        return Buffer.concat([header, this.payload]);
    }
}

function demonstrateUDP() {
    console.log("\nUDP");
    console.log("-".repeat(72));

    const datagram = new UDPDatagram(
        50000,
        53,
        "DNS query payload"
    );

    console.log(`Encoded UDP datagram: ${datagram.encode().toString("hex")}`);
    console.log(
        "UDP provides ports and a datagram transport but does not itself " +
        "provide TCP-style connection establishment and retransmission."
    );
}

// ---------------------------------------------------------------------------
// 10. TCP STATE MACHINE
// ---------------------------------------------------------------------------

const TCPStates = Object.freeze({
    CLOSED: "CLOSED",
    LISTEN: "LISTEN",
    SYN_SENT: "SYN-SENT",
    SYN_RECEIVED: "SYN-RECEIVED",
    ESTABLISHED: "ESTABLISHED"
});

class TCPEndpoint {
    constructor(name) {
        this.name = name;
        this.state = TCPStates.CLOSED;
        this.sequenceNumber = 0;
        this.acknowledgmentNumber = 0;
    }

    listen() {
        this.state = TCPStates.LISTEN;
    }

    sendSYN() {
        if (this.state !== TCPStates.CLOSED) {
            throw new Error("SYN requires CLOSED state in this model");
        }

        this.sequenceNumber = 1000 + Math.floor(Math.random() * 9000);
        this.state = TCPStates.SYN_SENT;
    }

    receiveSYN(sequenceNumber) {
        if (this.state !== TCPStates.LISTEN) {
            throw new Error("Server is not listening");
        }

        this.acknowledgmentNumber = sequenceNumber + 1;
        this.sequenceNumber = 2000 + Math.floor(Math.random() * 9000);
        this.state = TCPStates.SYN_RECEIVED;
    }

    receiveSYNACK(sequenceNumber) {
        if (this.state !== TCPStates.SYN_SENT) {
            throw new Error("Unexpected SYN-ACK");
        }

        this.acknowledgmentNumber = sequenceNumber + 1;
        this.state = TCPStates.ESTABLISHED;
    }

    receiveACK() {
        if (this.state !== TCPStates.SYN_RECEIVED) {
            throw new Error("Unexpected ACK");
        }

        this.state = TCPStates.ESTABLISHED;
    }
}

function demonstrateTCPHandshake() {
    console.log("\nTCP THREE-WAY HANDSHAKE");
    console.log("-".repeat(72));

    const client = new TCPEndpoint("client");
    const server = new TCPEndpoint("server");

    server.listen();
    client.sendSYN();

    console.log(`1. Client -> SYN, state=${client.state}`);

    server.receiveSYN(client.sequenceNumber);

    console.log(`2. Server -> SYN-ACK, state=${server.state}`);

    client.receiveSYNACK(server.sequenceNumber);

    console.log(`3. Client -> ACK, state=${client.state}`);

    server.receiveACK();

    console.log(`Client: ${client.state}`);
    console.log(`Server: ${server.state}`);
}

// ---------------------------------------------------------------------------
// 11. TCP RELIABILITY SIMULATION
// ---------------------------------------------------------------------------

class ReliableChannel {
    constructor(lossProbability) {
        if (lossProbability < 0 || lossProbability > 1) {
            throw new Error("Loss probability must be between 0 and 1");
        }

        this.lossProbability = lossProbability;
    }

    send(packet) {
        packet.attempts += 1;

        if (Math.random() < this.lossProbability) {
            return false;
        }

        packet.acknowledged = true;
        return true;
    }
}

function demonstrateReliability() {
    console.log("\nRELIABLE DELIVERY SIMULATION");
    console.log("-".repeat(72));

    const channel = new ReliableChannel(0.3);

    const packets = Array.from(
        { length: 5 },
        (_, index) => ({
            sequenceNumber: index + 1,
            payload: `payload-${index + 1}`,
            attempts: 0,
            acknowledged: false
        })
    );

    for (const packet of packets) {
        while (!packet.acknowledged && packet.attempts < 10) {
            if (channel.send(packet)) {
                console.log(
                    `Sequence ${packet.sequenceNumber}: ` +
                    `ACK after ${packet.attempts} attempt(s)`
                );
            } else {
                console.log(
                    `Sequence ${packet.sequenceNumber}: ` +
                    `lost, retransmitting`
                );
            }
        }

        if (!packet.acknowledged) {
            console.log(
                `Sequence ${packet.sequenceNumber}: transmission failed`
            );
        }
    }
}

// ---------------------------------------------------------------------------
// 12. PORTS
// ---------------------------------------------------------------------------

const commonPorts = {
    22: "SSH",
    25: "SMTP",
    53: "DNS",
    67: "DHCP server",
    68: "DHCP client",
    80: "HTTP",
    110: "POP3",
    123: "NTP",
    143: "IMAP",
    443: "HTTPS",
    3306: "MySQL",
    5432: "PostgreSQL",
    6379: "Redis"
};

function demonstratePorts() {
    console.log("\nTRANSPORT PORTS");
    console.log("-".repeat(72));

    for (const port of [22, 53, 80, 443, 5432, 9999]) {
        console.log(
            `${port}: ${commonPorts[port] || "No common mapping in this table"}`
        );
    }
}

// ---------------------------------------------------------------------------
// 13. DNS CACHE
// ---------------------------------------------------------------------------

class DNSCache {
    constructor() {
        this.records = new Map();
    }

    set(name, type, value, ttlSeconds) {
        const key = `${name.toLowerCase()}|${type}`;

        this.records.set(key, {
            name,
            type,
            value,
            expiresAt: Date.now() + ttlSeconds * 1000
        });
    }

    get(name, type) {
        const key = `${name.toLowerCase()}|${type}`;
        const record = this.records.get(key);

        if (!record) {
            return null;
        }

        if (Date.now() >= record.expiresAt) {
            this.records.delete(key);
            return null;
        }

        return record;
    }
}

function demonstrateDNS() {
    console.log("\nDNS");
    console.log("-".repeat(72));

    const cache = new DNSCache();

    cache.set(
        "example.com",
        "A",
        "93.184.216.34",
        60
    );

    const result = cache.get("EXAMPLE.COM", "A");

    console.log(
        result
            ? `${result.name} ${result.type} ${result.value}`
            : "DNS cache miss"
    );

    console.log(
        "DNS can represent A, AAAA, MX, CNAME, NS and TXT records."
    );
}

// ---------------------------------------------------------------------------
// 14. HTTP
// ---------------------------------------------------------------------------

class HTTPRequest {
    constructor(method, path, headers = {}, body = "") {
        this.method = method;
        this.path = path;
        this.headers = headers;
        this.body = body;
    }

    serialize() {
        const headerLines = Object.entries(this.headers)
            .map(([name, value]) => `${name}: ${value}`);

        return [
            `${this.method} ${this.path} HTTP/1.1`,
            ...headerLines,
            "",
            this.body
        ].join("\r\n");
    }
}

function demonstrateHTTP() {
    console.log("\nHTTP");
    console.log("-".repeat(72));

    const request = new HTTPRequest(
        "GET",
        "/products",
        {
            Host: "example.com",
            Accept: "application/json",
            Connection: "close"
        }
    );

    console.log(request.serialize());
}

// ---------------------------------------------------------------------------
// 15. DHCP
// ---------------------------------------------------------------------------

function demonstrateDHCP() {
    console.log("\nDHCP");
    console.log("-".repeat(72));

    [
        "DHCPDISCOVER: discover available servers",
        "DHCPOFFER: server offers configuration",
        "DHCPREQUEST: client requests the offer",
        "DHCPACK: server confirms the lease"
    ].forEach(step => console.log(step));

    console.log(
        "A DHCP lease commonly supplies an IP address, subnet mask, " +
        "gateway and DNS configuration."
    );
}

// ---------------------------------------------------------------------------
// 16. NAT
// ---------------------------------------------------------------------------

class NATTable {
    constructor(publicIP) {
        this.publicIP = publicIP;
        this.nextPort = 40000;
        this.mappings = new Map();
    }

    translate(privateIP, privatePort, destinationIP, destinationPort) {
        const key =
            `${privateIP}:${privatePort}->` +
            `${destinationIP}:${destinationPort}`;

        if (this.mappings.has(key)) {
            return this.mappings.get(key);
        }

        const mapping = {
            privateIP,
            privatePort,
            publicIP: this.publicIP,
            publicPort: this.nextPort++,
            destinationIP,
            destinationPort
        };

        this.mappings.set(key, mapping);

        return mapping;
    }
}

function demonstrateNAT() {
    console.log("\nNAT");
    console.log("-".repeat(72));

    const nat = new NATTable("203.0.113.10");

    const mapping = nat.translate(
        "192.168.1.20",
        51000,
        "93.184.216.34",
        443
    );

    console.log(
        `${mapping.privateIP}:${mapping.privatePort} -> ` +
        `${mapping.publicIP}:${mapping.publicPort}`
    );
}

// ---------------------------------------------------------------------------
// 17. MTU
// ---------------------------------------------------------------------------

function fragmentPayload(payload, mtu, ipHeaderSize = 20) {
    if (mtu <= ipHeaderSize) {
        throw new Error("MTU must exceed the IP header size");
    }

    const maxPayload = Math.floor(
        (mtu - ipHeaderSize) / 8
    ) * 8;

    if (maxPayload <= 0) {
        throw new Error("No valid aligned fragment size");
    }

    const fragments = [];

    for (
        let offset = 0;
        offset < payload.length;
        offset += maxPayload
    ) {
        fragments.push(
            payload.slice(offset, offset + maxPayload)
        );
    }

    return fragments;
}

function demonstrateMTU() {
    console.log("\nMTU");
    console.log("-".repeat(72));

    const payload = Buffer.alloc(100, 0xab);

    const fragments = fragmentPayload(
        payload,
        44,
        20
    );

    console.log(
        `Payload: ${payload.length} bytes`
    );

    console.log(
        `Fragments: ${fragments.map(fragment => fragment.length).join(", ")}`
    );

    console.log(
        "Fragmentation can introduce overhead and operational complexity. " +
        "Path-MTU discovery can reduce the need for fragmentation."
    );
}

// ---------------------------------------------------------------------------
// 18. APPLICATION DATA INTEGRITY
// ---------------------------------------------------------------------------

function demonstrateHashing() {
    console.log("\nAPPLICATION DATA INTEGRITY");
    console.log("-".repeat(72));

    const payload = Buffer.from("network message");

    const digest = crypto
        .createHash("sha256")
        .update(payload)
        .digest("hex");

    console.log(`Payload: ${payload.toString()}`);
    console.log(`SHA-256: ${digest}`);

    console.log(
        "A hash detects changes but does not by itself authenticate the sender."
    );
}

// ---------------------------------------------------------------------------
// 19. REAL TCP SOCKET CASE
// ---------------------------------------------------------------------------

function demonstrateRealTCPSocket() {
    return new Promise((resolve, reject) => {
        console.log("\nREAL LOOPBACK TCP SOCKET");
        console.log("-".repeat(72));

        const server = net.createServer(connection => {
            connection.on("data", data => {
                connection.write(data.toString().toUpperCase());
            });

            connection.on("error", reject);
        });

        server.on("error", reject);

        server.listen(0, "127.0.0.1", () => {
            const address = server.address();

            if (!address || typeof address === "string") {
                server.close();
                reject(new Error("Could not determine listening port"));
                return;
            }

            console.log(
                `Server listening on ${address.address}:${address.port}`
            );

            const client = net.createConnection({
                host: "127.0.0.1",
                port: address.port
            });

            let response = "";

            client.on("data", data => {
                response += data.toString();

                if (response.length > 0) {
                    console.log(`Client received: ${response}`);

                    client.end();
                    server.close(() => resolve());
                }
            });

            client.on("connect", () => {
                client.write("hello TCP/IP");
            });

            client.on("error", error => {
                server.close();
                reject(error);
            });
        });
    });
}

// ---------------------------------------------------------------------------
// 20. TCP VS UDP
// ---------------------------------------------------------------------------

function compareTCPUDP() {
    console.log("\nTCP VS UDP");
    console.log("-".repeat(72));

    const rows = [
        ["Connection", "Connection-oriented", "Connectionless"],
        ["Ordering", "Ordered byte stream", "No inherent ordering"],
        ["Retransmission", "Built in", "Not built in"],
        ["Flow control", "Yes", "No TCP-style mechanism"],
        ["Congestion control", "Yes", "Not inherent"],
        ["Overhead", "Generally higher", "Generally lower"],
        ["Examples", "HTTP/HTTPS, SSH", "DNS, streaming, games"]
    ];

    console.log(
        "Property".padEnd(20) +
        "TCP".padEnd(28) +
        "UDP"
    );

    for (const row of rows) {
        console.log(
            row[0].padEnd(20) +
            row[1].padEnd(28) +
            row[2]
        );
    }
}

// ---------------------------------------------------------------------------
// 21. OSI COMPARISON
// ---------------------------------------------------------------------------

function compareOSIAndTCPIP() {
    console.log("\nOSI AND TCP/IP MAPPING");
    console.log("-".repeat(72));

    const mapping = [
        ["OSI Application", "TCP/IP Application"],
        ["OSI Presentation", "TCP/IP Application"],
        ["OSI Session", "TCP/IP Application"],
        ["OSI Transport", "TCP/IP Transport"],
        ["OSI Network", "TCP/IP Internet"],
        ["OSI Data Link", "TCP/IP Network Access"],
        ["OSI Physical", "TCP/IP Network Access"]
    ];

    for (const [osi, tcpip] of mapping) {
        console.log(`${osi.padEnd(28)} -> ${tcpip}`);
    }
}

// ---------------------------------------------------------------------------
// 22. SECURITY
// ---------------------------------------------------------------------------

function demonstrateSecurity() {
    console.log("\nSECURITY");
    console.log("-".repeat(72));

    const controls = [
        ["Network Access", "Use secure Wi-Fi and appropriate link controls."],
        ["Internet", "Use routing controls, filtering and segmentation."],
        ["Transport", "Limit exposed ports and validate traffic."],
        ["Application", "Use TLS, authentication and authorization."],
        ["DNS", "Protect DNS against spoofing and manipulation."]
    ];

    for (const [layer, control] of controls) {
        console.log(`${layer}: ${control}`);
    }
}

// ---------------------------------------------------------------------------
// 23. PERFORMANCE
// ---------------------------------------------------------------------------

function demonstratePerformance() {
    console.log("\nPERFORMANCE");
    console.log("-".repeat(72));

    const factors = {
        Bandwidth: "Capacity for transferring data.",
        Latency: "Delay between sending and receiving.",
        Jitter: "Variation in packet delay.",
        PacketLoss: "Packets that do not reach the destination.",
        MTU: "Maximum transmission-unit constraint.",
        RTT: "Round-trip time.",
        Window: "Amount of outstanding transport data."
    };

    for (const [factor, explanation] of Object.entries(factors)) {
        console.log(`${factor.padEnd(14)}: ${explanation}`);
    }
}

// ---------------------------------------------------------------------------
// 24. TROUBLESHOOTING
// ---------------------------------------------------------------------------

function troubleshootingChecklist() {
    console.log("\nTROUBLESHOOTING");
    console.log("-".repeat(72));

    const checks = [
        "Check physical or wireless connectivity.",
        "Check network-interface status.",
        "Check MAC and link configuration.",
        "Check IP address and subnet.",
        "Check default gateway.",
        "Check routing table.",
        "Test local gateway reachability.",
        "Test remote IP connectivity.",
        "Test DNS separately from IP connectivity.",
        "Test the required transport port.",
        "Inspect application-layer responses.",
        "Use packet captures when necessary."
    ];

    checks.forEach(
        (check, index) => console.log(`${index + 1}. ${check}`)
    );
}

// ---------------------------------------------------------------------------
// 25. EDGE CASES
// ---------------------------------------------------------------------------

function demonstrateEdgeCases() {
    console.log("\nEDGE CASES");
    console.log("-".repeat(72));

    const cases = [
        "A host may have multiple IP addresses.",
        "IPv4 and IPv6 can operate simultaneously.",
        "DNS may return multiple addresses.",
        "Ping failure does not prove that all application traffic fails.",
        "A reachable IP does not prove that a TCP port is open.",
        "An open TCP port does not prove that the application protocol is healthy.",
        "NAT can change the visible source address and source port.",
        "Firewalls can block traffic independently of routing.",
        "UDP applications must implement reliability themselves when they require it.",
        "TCP retransmissions can result from loss, congestion or path problems."
    ];

    cases.forEach(item => console.log(`- ${item}`));
}

// ---------------------------------------------------------------------------
// 26. MAIN
// ---------------------------------------------------------------------------

async function main() {
    console.log("=".repeat(72));
    console.log("TCP/IP MODEL: COMPREHENSIVE JAVASCRIPT STUDY PROGRAM");
    console.log("=".repeat(72));

    showModel();
    demonstrateEncapsulation();
    demonstrateMAC();
    demonstrateIPv4();
    demonstrateIPv6();
    demonstrateSubnetting();
    demonstrateRouting();
    demonstrateChecksum();
    demonstrateUDP();
    demonstrateTCPHandshake();
    demonstrateReliability();
    demonstratePorts();
    demonstrateDNS();
    demonstrateHTTP();
    demonstrateDHCP();
    demonstrateNAT();
    demonstrateMTU();
    demonstrateHashing();

    try {
        await demonstrateRealTCPSocket();
    } catch (error) {
        console.log(
            `Loopback socket demonstration could not run: ${error.message}`
        );
    }

    compareTCPUDP();
    compareOSIAndTCPIP();
    demonstrateSecurity();
    demonstratePerformance();
    troubleshootingChecklist();
    demonstrateEdgeCases();

    console.log("\nSTUDY COMPLETE");
    console.log(
        "TCP/IP separates networking responsibilities into layers while " +
        "different protocols cooperate to move application data."
    );
}

main().catch(error => {
    console.error("Program failed:", error);
    process.exitCode = 1;
});
