/*
 * OSI Model: JavaScript Study Implementation
 *
 * This file complements the Python implementation by using JavaScript
 * objects, classes, Maps, asynchronous functions, validation, event-driven
 * behavior, and packet-processing simulations.
 *
 * Run with:
 *   node osi_models.js
 */

"use strict";

const OSILayer = Object.freeze({
    PHYSICAL: 1,
    DATA_LINK: 2,
    NETWORK: 3,
    TRANSPORT: 4,
    SESSION: 5,
    PRESENTATION: 6,
    APPLICATION: 7
});

const LAYER_NAMES = Object.freeze({
    1: "Physical",
    2: "Data Link",
    3: "Network",
    4: "Transport",
    5: "Session",
    6: "Presentation",
    7: "Application"
});

const PDU_NAMES = Object.freeze({
    1: "Bits",
    2: "Frame",
    3: "Packet",
    4: "Segment / Datagram",
    5: "Data",
    6: "Data",
    7: "Data"
});

function printTitle(title) {
    console.log(`\n${"=".repeat(78)}`);
    console.log(title);
    console.log("=".repeat(78));
}

function demonstrateLayers() {
    printTitle("1. Seven OSI Layers");

    const layers = [
        [1, "Physical", "Bits", "Signals, cables, fiber, radio"],
        [2, "Data Link", "Frame", "Ethernet, Wi-Fi, MAC addressing"],
        [3, "Network", "Packet", "IPv4, IPv6, routing"],
        [4, "Transport", "Segment/Datagram", "TCP, UDP, ports"],
        [5, "Session", "Data", "Session/dialog management"],
        [6, "Presentation", "Data", "Encoding, compression, encryption"],
        [7, "Application", "Data", "HTTP, DNS, SMTP, SSH"]
    ];

    for (const [number, name, pdu, examples] of layers) {
        console.log(
            `L${number} ${name.padEnd(15)} PDU=${pdu.padEnd(17)} ${examples}`
        );
    }
}

function demonstrateEncapsulation() {
    printTitle("2. Encapsulation");

    const applicationData = "GET /index.html HTTP/1.1";
    const tlsData = `TLS(${applicationData})`;
    const tcpSegment = `TCP[51500 -> 443] ${tlsData}`;
    const ipPacket = `IP[192.168.1.20 -> 203.0.113.10] ${tcpSegment}`;
    const ethernetFrame = `ETH[AA:BB:CC:DD:EE:01 -> AA:BB:CC:DD:EE:FE] ${ipPacket}`;

    console.log("Application:", applicationData);
    console.log("Presentation:", tlsData);
    console.log("Transport:", tcpSegment);
    console.log("Network:", ipPacket);
    console.log("Data Link:", ethernetFrame);
    console.log("Physical: binary signals representing the frame");

    console.log("\nDecapsulation removes these wrappers in reverse order.");
}

class TCPSegment {
    constructor(sourcePort, destinationPort, sequenceNumber, acknowledgmentNumber, flags, payload = "") {
        this.sourcePort = sourcePort;
        this.destinationPort = destinationPort;
        this.sequenceNumber = sequenceNumber;
        this.acknowledgmentNumber = acknowledgmentNumber;
        this.flags = flags;
        this.payload = payload;
    }

    describe() {
        return {
            ports: `${this.sourcePort} -> ${this.destinationPort}`,
            sequenceNumber: this.sequenceNumber,
            acknowledgmentNumber: this.acknowledgmentNumber,
            flags: this.flags.join(", "),
            payload: this.payload
        };
    }
}

function demonstrateTCPHandshake() {
    printTitle("3. TCP Three-Way Handshake");

    const clientPort = 51500;
    const serverPort = 443;
    const clientISN = 10000;
    const serverISN = 70000;

    const handshake = [
        new TCPSegment(clientPort, serverPort, clientISN, 0, ["SYN"]),
        new TCPSegment(serverPort, clientPort, serverISN, clientISN + 1, ["SYN", "ACK"]),
        new TCPSegment(clientPort, serverPort, clientISN + 1, serverISN + 1, ["ACK"])
    ];

    handshake.forEach((segment, index) => {
        console.log(`Message ${index + 1}:`, segment.describe());
    });
}

function demonstrateAddressing() {
    printTitle("4. Addressing");

    const macAddress = "AA:BB:CC:DD:EE:01";
    const ipAddress = "192.168.1.20";
    const destinationPort = 443;

    console.log("Layer 2 MAC:", macAddress);
    console.log("Layer 3 IP:", ipAddress);
    console.log("Layer 4 port:", destinationPort);

    console.log("\nA complete endpoint can be represented as:");
    console.log(`${ipAddress}:${destinationPort}`);
}

function ipv4ToInteger(address) {
    const octets = address.split(".").map(Number);

    if (
        octets.length !== 4 ||
        octets.some(
            octet => !Number.isInteger(octet) || octet < 0 || octet > 255
        )
    ) {
        throw new Error(`Invalid IPv4 address: ${address}`);
    }

    return (
        (((octets[0] << 24) >>> 0) |
            (octets[1] << 16) |
            (octets[2] << 8) |
            octets[3]) >>> 0
    );
}

function isValidPort(port) {
    return Number.isInteger(port) && port >= 1 && port <= 65535;
}

function demonstrateValidation() {
    printTitle("5. Network Validation");

    const addresses = [
        "192.168.1.1",
        "10.0.0.5",
        "256.1.1.1",
        "192.168.1"
    ];

    for (const address of addresses) {
        try {
            const value = ipv4ToInteger(address);
            console.log(`${address.padEnd(16)} valid -> ${value}`);
        } catch (error) {
            console.log(`${address.padEnd(16)} invalid -> ${error.message}`);
        }
    }

    const ports = [0, 22, 443, 65535, 65536];

    for (const port of ports) {
        console.log(`Port ${port}: ${isValidPort(port) ? "valid" : "invalid"}`);
    }
}

class EthernetSwitch {
    constructor() {
        this.macTable = new Map();
    }

    learn(macAddress, port) {
        this.macTable.set(macAddress.toUpperCase(), port);
    }

    forward(destinationMac) {
        const normalized = destinationMac.toUpperCase();
        return this.macTable.get(normalized) ?? "FLOOD";
    }
}

function demonstrateSwitching() {
    printTitle("6. Layer 2 Switching");

    const switchDevice = new EthernetSwitch();

    switchDevice.learn("AA:AA:AA:AA:AA:10", "Port 1");
    switchDevice.learn("AA:AA:AA:AA:AA:20", "Port 2");
    switchDevice.learn("AA:AA:AA:AA:AA:30", "Port 3");

    console.log(
        "Known destination:",
        switchDevice.forward("AA:AA:AA:AA:AA:20")
    );

    console.log(
        "Unknown destination:",
        switchDevice.forward("AA:AA:AA:AA:AA:99")
    );
}

class RouteTable {
    constructor() {
        this.routes = [];
    }

    addRoute(networkAddress, prefixLength, nextHop) {
        if (
            !Number.isInteger(prefixLength) ||
            prefixLength < 0 ||
            prefixLength > 32
        ) {
            throw new Error("IPv4 prefix length must be between 0 and 32.");
        }

        this.routes.push({
            networkAddress,
            prefixLength,
            nextHop
        });
    }

    /*
     * This simplified matcher converts IPv4 addresses to integers and applies
     * the CIDR mask. Longest-prefix matching selects the most specific route.
     */
    lookup(destination) {
        const destinationInteger = ipv4ToInteger(destination);

        const matches = this.routes.filter(route => {
            const networkInteger = ipv4ToInteger(route.networkAddress);

            if (route.prefixLength === 0) {
                return true;
            }

            const mask =
                (0xffffffff << (32 - route.prefixLength)) >>> 0;

            return (
                (destinationInteger & mask) >>> 0 ===
                (networkInteger & mask) >>> 0
            );
        });

        if (matches.length === 0) {
            return null;
        }

        return matches.reduce((best, current) =>
            current.prefixLength > best.prefixLength ? current : best
        );
    }
}

function demonstrateRouting() {
    printTitle("7. Layer 3 Routing");

    const routingTable = new RouteTable();

    routingTable.addRoute("0.0.0.0", 0, "Internet Gateway");
    routingTable.addRoute("10.0.0.0", 8, "Private Router");
    routingTable.addRoute("10.20.0.0", 16, "Data Center Router");
    routingTable.addRoute("10.20.30.0", 24, "Application Router");

    const destination = "10.20.30.44";
    const route = routingTable.lookup(destination);

    console.log(`Destination: ${destination}`);
    console.log("Selected route:", route);
}

function demonstrateTransportComparison() {
    printTitle("8. TCP and UDP");

    const comparison = [
        ["Connection", "TCP-oriented connection", "UDP connectionless"],
        ["Reliability", "Acknowledgments/retransmission", "Not built into UDP"],
        ["Ordering", "Ordered byte stream", "No ordering guarantee"],
        ["Overhead", "Higher", "Lower"],
        ["Typical use", "HTTPS, SSH", "DNS, real-time protocols"]
    ];

    console.table(
        comparison.map(([property, tcp, udp]) => ({
            Property: property,
            TCP: tcp,
            UDP: udp
        }))
    );
}

function demonstrateDNS() {
    printTitle("9. DNS");

    const dnsCache = new Map([
        ["example.com", "93.184.216.34"],
        ["localhost", "127.0.0.1"]
    ]);

    const domain = "example.com";
    const address = dnsCache.get(domain);

    console.log(`Query: ${domain}`);

    if (address) {
        console.log(`Answer: ${address}`);
    } else {
        console.log("No cached answer; a DNS resolver would perform a lookup.");
    }
}

function demonstrateHTTP() {
    printTitle("10. HTTP");

    const request = [
        "GET /index.html HTTP/1.1",
        "Host: example.com",
        "Accept: text/html",
        "Connection: close",
        ""
    ].join("\r\n");

    console.log(request);

    console.log("\nTypical HTTPS stack:");
    console.log("HTTP -> TLS -> TCP -> IP -> Ethernet/Wi-Fi -> Physical medium");
}

function demonstrateModernStack() {
    printTitle("11. Modern Protocol Stacks");

    console.log("Traditional HTTPS:");
    console.log("HTTP -> TLS -> TCP -> IP -> Link");

    console.log("\nHTTP/3:");
    console.log("HTTP/3 -> QUIC -> UDP -> IP -> Link");

    console.log(
        "\nThe OSI model remains useful as a conceptual framework even when"
    );
    console.log(
        "modern protocols combine responsibilities that do not fit one layer exactly."
    );
}

class PacketTracer {
    constructor() {
        this.events = [];
    }

    record(layer, action, details) {
        this.events.push({
            layer,
            layerName: LAYER_NAMES[layer],
            action,
            details,
            timestamp: Date.now()
        });
    }

    print() {
        for (const event of this.events) {
            console.log(
                `L${event.layer} ${event.layerName.padEnd(14)} ` +
                `${event.action.padEnd(12)} ${event.details}`
            );
        }
    }
}

function demonstratePacketTrace() {
    printTitle("12. End-to-End Packet Trace");

    const tracer = new PacketTracer();

    tracer.record(7, "CREATE", "Browser creates HTTPS request");
    tracer.record(6, "PROTECT", "TLS protects application communication");
    tracer.record(5, "TRACK", "Session state is maintained");
    tracer.record(4, "SEGMENT", "TCP targets destination port 443");
    tracer.record(3, "ROUTE", "IP packet is routed toward remote network");
    tracer.record(2, "FRAME", "Frame targets the local next hop");
    tracer.record(1, "TRANSMIT", "Bits/signals travel over the medium");

    tracer.print();
}

function demonstrateAsyncNetworkBehavior() {
    printTitle("13. Asynchronous Network Behavior");

    /*
     * JavaScript's event-driven model is useful for demonstrating how an
     * application can start I/O and continue processing other work while
     * awaiting a result.
     */
    const simulatedNetworkRequest = new Promise(resolve => {
        setTimeout(() => {
            resolve({
                status: 200,
                layer: OSILayer.APPLICATION,
                message: "HTTP response received"
            });
        }, 100);
    });

    return simulatedNetworkRequest.then(response => {
        console.log("Asynchronous result:", response);
    });
}

function demonstrateSubnetConcept() {
    printTitle("14. CIDR Subnetting");

    const examples = [
        { network: "192.168.1.0", prefix: 24 },
        { network: "192.168.1.0", prefix: 26 },
        { network: "10.0.0.0", prefix: 8 }
    ];

    for (const item of examples) {
        const totalAddresses = 2 ** (32 - item.prefix);

        console.log(
            `${item.network}/${item.prefix}: ` +
            `${totalAddresses} total IPv4 addresses`
        );

        if (totalAddresses >= 4) {
            console.log(
                `Traditional usable-host count: ${totalAddresses - 2}`
            );
        }
    }
}

function demonstrateSecurity() {
    printTitle("15. Security Across OSI Layers");

    const controls = {
        1: "Physical access control and medium protection",
        2: "VLAN security, 802.1X, switch protections",
        3: "ACLs, segmentation, IPsec, routing security",
        4: "Firewalls and transport-port controls",
        5: "Session expiration and state validation",
        6: "TLS and certificate validation",
        7: "Authentication, authorization, input validation"
    };

    for (let layer = 1; layer <= 7; layer++) {
        console.log(
            `L${layer} ${LAYER_NAMES[layer].padEnd(14)} ${controls[layer]}`
        );
    }
}

function demonstratePerformance() {
    printTitle("16. Performance Considerations");

    const metrics = {
        "Physical": "Bandwidth, interference, signal quality",
        "Data Link": "Frame overhead and switching",
        "Network": "Routing, packet loss, MTU",
        "Transport": "RTT, congestion, retransmission",
        "Session": "Connection/session setup",
        "Presentation": "Encryption and compression cost",
        "Application": "Serialization and server processing"
    };

    for (const [layer, metric] of Object.entries(metrics)) {
        console.log(`${layer.padEnd(15)} ${metric}`);
    }
}

function demonstrateCommonMistakes() {
    printTitle("17. Common OSI Misconceptions");

    const mistakes = [
        "OSI is not a literal implementation required by every network stack.",
        "A protocol may perform responsibilities associated with multiple layers.",
        "A successful ping does not prove that an HTTP service is healthy.",
        "A MAC address and an IP address serve different addressing purposes.",
        "TCP delivery does not guarantee that an application successfully processed data.",
        "Security controls often cross OSI layer boundaries."
    ];

    mistakes.forEach((mistake, index) => {
        console.log(`${index + 1}. ${mistake}`);
    });
}

function demonstrateEventDrivenLayerProcessing() {
    printTitle("18. Event-Driven Packet Processing");

    const listeners = new Map();

    function on(eventName, handler) {
        if (!listeners.has(eventName)) {
            listeners.set(eventName, []);
        }
        listeners.get(eventName).push(handler);
    }

    function emit(eventName, data) {
        for (const handler of listeners.get(eventName) ?? []) {
            handler(data);
        }
    }

    on("frameReceived", frame => {
        console.log("Layer 2 received:", frame);
        emit("packetReady", {
            sourceIP: "192.168.1.20",
            destinationIP: "203.0.113.10"
        });
    });

    on("packetReady", packet => {
        console.log("Layer 3 forwarding decision:", packet);
        emit("segmentReady", {
            sourcePort: 51500,
            destinationPort: 443
        });
    });

    on("segmentReady", segment => {
        console.log("Layer 4 delivered to port:", segment.destinationPort);
    });

    emit("frameReceived", {
        sourceMAC: "AA:BB:CC:DD:EE:01",
        destinationMAC: "AA:BB:CC:DD:EE:FE"
    });
}

function runAssertions() {
    printTitle("19. Self-Tests");

    console.assert(ipv4ToInteger("127.0.0.1") === 2130706433);
    console.assert(isValidPort(443));
    console.assert(!isValidPort(0));
    console.assert(!isValidPort(65536));

    const table = new RouteTable();
    table.addRoute("0.0.0.0", 0, "Default");
    table.addRoute("10.0.0.0", 8, "Private");
    table.addRoute("10.20.30.0", 24, "Application");

    const result = table.lookup("10.20.30.44");
    console.assert(result.nextHop === "Application");

    console.log("All JavaScript self-tests passed.");
}

async function main() {
    printTitle("OSI MODEL JAVASCRIPT STUDY PROGRAM");

    demonstrateLayers();
    demonstrateEncapsulation();
    demonstrateTCPHandshake();
    demonstrateAddressing();
    demonstrateValidation();
    demonstrateSwitching();
    demonstrateRouting();
    demonstrateTransportComparison();
    demonstrateDNS();
    demonstrateHTTP();
    demonstrateModernStack();
    demonstratePacketTrace();
    await demonstrateAsyncNetworkBehavior();
    demonstrateSubnetConcept();
    demonstrateSecurity();
    demonstratePerformance();
    demonstrateCommonMistakes();
    demonstrateEventDrivenLayerProcessing();
    runAssertions();

    printTitle("END OF OSI MODEL JAVASCRIPT STUDY PROGRAM");
}

main().catch(error => {
    console.error("Program failed:", error.message);
    process.exitCode = 1;
});
