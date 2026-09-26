"use strict";

/*
 * TCP AND UDP: JAVASCRIPT PRACTICAL STUDY FILE
 *
 * This file uses Node.js built-in modules only.
 *
 * Topics demonstrated:
 * - Ports and endpoints
 * - TCP connection-oriented communication
 * - TCP byte-stream behavior
 * - TCP client/server implementation
 * - UDP datagram communication
 * - Timeouts and retries
 * - Application-level sequencing and duplicate detection
 * - Packet validation
 * - Asynchronous event-driven networking
 * - Performance and security considerations
 */

const net = require("net");
const dgram = require("dgram");
const crypto = require("crypto");


// ============================================================================
// 1. BASIC NETWORK CONCEPTS
// ============================================================================

function printSection(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}

function demonstrateEndpoints() {
    printSection("1. IP ADDRESSES, PORTS, AND ENDPOINTS");

    const endpoint = {
        protocol: "TCP",
        address: "127.0.0.1",
        port: 8080
    };

    console.log("Protocol:", endpoint.protocol);
    console.log("Address:", endpoint.address);
    console.log("Port:", endpoint.port);

    console.log(`
A transport endpoint can be described conceptually as:

    protocol + IP address + port

A TCP connection is associated with source and destination endpoints.
The operating system uses ports to deliver incoming transport traffic to
the appropriate application socket.
`);
}


// ============================================================================
// 2. TCP THREE-WAY HANDSHAKE
// ============================================================================

function demonstrateThreeWayHandshake() {
    printSection("2. TCP THREE-WAY HANDSHAKE");

    const clientInitialSequence = 1000;
    const serverInitialSequence = 5000;

    console.log("1. Client -> Server: SYN");
    console.log("   Sequence:", clientInitialSequence);

    console.log("2. Server -> Client: SYN + ACK");
    console.log("   Sequence:", serverInitialSequence);
    console.log(
        "   Acknowledgement:",
        clientInitialSequence + 1
    );

    console.log("3. Client -> Server: ACK");
    console.log(
        "   Acknowledgement:",
        serverInitialSequence + 1
    );

    console.log(`
The handshake synchronizes sequence-number state and establishes the TCP
connection before application data is normally exchanged.
`);
}


// ============================================================================
// 3. TCP BYTE STREAM
// ============================================================================

function demonstrateTcpByteStream() {
    printSection("3. TCP IS A BYTE STREAM");

    const firstWrite = Buffer.from("HELLO");
    const secondWrite = Buffer.from("WORLD");

    const stream = Buffer.concat([firstWrite, secondWrite]);

    console.log("Application write 1:", firstWrite.toString());
    console.log("Application write 2:", secondWrite.toString());
    console.log("Combined stream:", stream.toString());

    console.log(`
TCP does not preserve application-level message boundaries.

A single data write can be split across multiple reads, and multiple writes
can be observed together. Application protocols therefore need explicit
framing when individual messages matter.
`);
}


// ============================================================================
// 4. LENGTH-PREFIXED TCP FRAMING
// ============================================================================

function encodeMessage(message) {
    const payload = Buffer.from(message, "utf8");

    if (payload.length > 0xffffffff) {
        throw new Error("Message is too large");
    }

    const header = Buffer.alloc(4);
    header.writeUInt32BE(payload.length, 0);

    return Buffer.concat([header, payload]);
}

function extractMessages(buffer) {
    const messages = [];
    let offset = 0;

    while (buffer.length - offset >= 4) {
        const length = buffer.readUInt32BE(offset);

        if (length > 10 * 1024 * 1024) {
            throw new Error("Frame exceeds configured maximum size");
        }

        if (buffer.length - offset - 4 < length) {
            break;
        }

        const start = offset + 4;
        const end = start + length;

        messages.push(buffer.subarray(start, end).toString("utf8"));
        offset = end;
    }

    return {
        messages,
        remaining: buffer.subarray(offset)
    };
}

function demonstrateFraming() {
    printSection("4. LENGTH-PREFIXED TCP MESSAGE FRAMING");

    const frame1 = encodeMessage("first");
    const frame2 = encodeMessage("second");

    // TCP may deliver both frames together, so the receiver parses them
    // from a byte buffer rather than assuming one socket event equals one
    // application message.
    const combined = Buffer.concat([frame1, frame2]);

    const result = extractMessages(combined);

    console.log("Decoded messages:", result.messages);
    console.log("Remaining bytes:", result.remaining.length);
}


// ============================================================================
// 5. TCP SERVER
// ============================================================================

function startTcpServer() {
    return new Promise((resolve, reject) => {
        const server = net.createServer((socket) => {
            console.log(
                "TCP client connected:",
                socket.remoteAddress,
                socket.remotePort
            );

            socket.setTimeout(3000);

            let receiveBuffer = Buffer.alloc(0);

            socket.on("data", (chunk) => {
                receiveBuffer = Buffer.concat([receiveBuffer, chunk]);

                try {
                    const parsed = extractMessages(receiveBuffer);
                    receiveBuffer = parsed.remaining;

                    for (const message of parsed.messages) {
                        console.log("Server received:", message);

                        const response = encodeMessage(
                            `Server received: ${message}`
                        );

                        // write() returns false when the internal buffer is
                        // full. Production code should respect backpressure.
                        const writable = socket.write(response);

                        if (!writable) {
                            console.log("TCP write buffer is full");
                        }
                    }
                } catch (error) {
                    socket.destroy(error);
                }
            });

            socket.on("timeout", () => {
                console.log("TCP socket timed out");
                socket.end();
            });

            socket.on("error", (error) => {
                console.error("TCP client error:", error.message);
            });

            socket.on("close", () => {
                console.log("TCP connection closed");
            });
        });

        server.on("error", reject);

        // Port 0 asks the operating system to select an available ephemeral
        // port, which is useful for demonstrations and automated tests.
        server.listen(0, "127.0.0.1", () => {
            const address = server.address();
            console.log("TCP server listening on:", address);

            resolve({ server, port: address.port });
        });
    });
}


// ============================================================================
// 6. TCP CLIENT
// ============================================================================

function runTcpClient(port) {
    return new Promise((resolve, reject) => {
        const socket = net.createConnection({
            host: "127.0.0.1",
            port
        });

        socket.setTimeout(3000);

        let receiveBuffer = Buffer.alloc(0);

        socket.on("connect", () => {
            console.log("TCP client connected");

            const first = encodeMessage("Hello");
            const second = encodeMessage("TCP");

            socket.write(Buffer.concat([first, second]));
        });

        socket.on("data", (chunk) => {
            receiveBuffer = Buffer.concat([receiveBuffer, chunk]);

            try {
                const parsed = extractMessages(receiveBuffer);
                receiveBuffer = parsed.remaining;

                for (const message of parsed.messages) {
                    console.log("Client received:", message);
                }
            } catch (error) {
                socket.destroy(error);
                reject(error);
            }
        });

        socket.on("timeout", () => {
            socket.destroy(new Error("TCP client timeout"));
        });

        socket.on("error", reject);

        socket.on("close", () => {
            resolve();
        });
    });
}


// ============================================================================
// 7. UDP DATAGRAM SERVER
// ============================================================================

function startUdpServer() {
    return new Promise((resolve, reject) => {
        const server = dgram.createSocket("udp4");

        server.on("error", (error) => {
            console.error("UDP server error:", error.message);
            server.close();
            reject(error);
        });

        server.on("message", (message, remote) => {
            console.log(
                "UDP server received:",
                message.toString(),
                "from",
                `${remote.address}:${remote.port}`
            );

            server.send(
                Buffer.from(`UDP response: ${message.toString()}`),
                remote.port,
                remote.address
            );
        });

        server.bind(0, "127.0.0.1", () => {
            const address = server.address();
            console.log("UDP server listening on:", address);
            resolve({ server, port: address.port });
        });
    });
}


// ============================================================================
// 8. UDP CLIENT WITH TIMEOUT
// ============================================================================

function sendUdpRequest(port, payload, timeoutMs = 1000) {
    return new Promise((resolve, reject) => {
        const client = dgram.createSocket("udp4");

        const timer = setTimeout(() => {
            client.close();
            reject(new Error("UDP request timed out"));
        }, timeoutMs);

        client.once("message", (message) => {
            clearTimeout(timer);
            client.close();
            resolve(message);
        });

        client.once("error", (error) => {
            clearTimeout(timer);
            client.close();
            reject(error);
        });

        client.send(
            Buffer.from(payload),
            port,
            "127.0.0.1",
            (error) => {
                if (error) {
                    clearTimeout(timer);
                    client.close();
                    reject(error);
                }
            }
        );
    });
}


// ============================================================================
// 9. APPLICATION-LEVEL UDP RELIABILITY
// ============================================================================

class ReliableUdpPacket {
    constructor(sequence, payload) {
        if (!Number.isInteger(sequence) || sequence < 0) {
            throw new Error("Invalid sequence number");
        }

        this.sequence = sequence;
        this.payload = Buffer.from(payload);
    }

    encode() {
        const packet = {
            version: 1,
            sequence: this.sequence,
            payload: this.payload.toString("base64")
        };

        return Buffer.from(JSON.stringify(packet), "utf8");
    }

    static decode(buffer) {
        let packet;

        try {
            packet = JSON.parse(buffer.toString("utf8"));
        } catch {
            throw new Error("Malformed JSON packet");
        }

        if (packet.version !== 1) {
            throw new Error("Unsupported protocol version");
        }

        if (!Number.isInteger(packet.sequence) || packet.sequence < 0) {
            throw new Error("Invalid sequence number");
        }

        if (typeof packet.payload !== "string") {
            throw new Error("Invalid payload");
        }

        return new ReliableUdpPacket(
            packet.sequence,
            Buffer.from(packet.payload, "base64")
        );
    }
}

function demonstrateReliableUdpDesign() {
    printSection("9. APPLICATION-LEVEL RELIABILITY OVER UDP");

    const packets = [
        new ReliableUdpPacket(2, "third"),
        new ReliableUdpPacket(0, "first"),
        new ReliableUdpPacket(2, "duplicate"),
        new ReliableUdpPacket(1, "second")
    ];

    const received = new Map();

    for (const packet of packets) {
        // A sequence number lets the application identify duplicates.
        if (!received.has(packet.sequence)) {
            received.set(packet.sequence, packet);
        }
    }

    const ordered = [...received.values()]
        .sort((a, b) => a.sequence - b.sequence)
        .map(packet => packet.payload.toString());

    console.log("Ordered unique messages:", ordered);

    console.log(`
UDP itself does not provide ordering, retransmission, or duplicate
suppression. An application protocol can implement these features, but it
must also define acknowledgement behavior, retry limits, timers, and
resource-management rules.
`);
}


// ============================================================================
// 10. CHECKSUM / HASH DEMONSTRATION
// ============================================================================

function demonstrateIntegrity() {
    printSection("10. DATA INTEGRITY");

    const message = Buffer.from("transport data");

    const digest = crypto
        .createHash("sha256")
        .update(message)
        .digest("hex");

    console.log("SHA-256:", digest);

    console.log(`
A cryptographic hash detects changes to data when the expected digest is
trusted. A hash alone does not authenticate the sender.

Transport checksums are intended for error detection and are not a replacement
for cryptographic security.
`);
}


// ============================================================================
// 11. TCP TERMINATION
// ============================================================================

function demonstrateTermination() {
    printSection("11. TCP CONNECTION TERMINATION");

    console.log(`
TCP is full duplex. Closing one direction does not necessarily mean that
both directions have immediately stopped.

A simplified graceful close involves FIN and ACK exchanges:

    A -> FIN
    B -> ACK
    B -> FIN
    A -> ACK

Operating systems maintain TCP states such as ESTABLISHED, FIN_WAIT,
CLOSE_WAIT, LAST_ACK, and TIME_WAIT.
`);
}


// ============================================================================
// 12. FLOW CONTROL AND CONGESTION CONTROL
// ============================================================================

function demonstrateControlConcepts() {
    printSection("12. FLOW CONTROL AND CONGESTION CONTROL");

    const receiveWindow = 32768;
    const congestionWindow = 16384;

    console.log(
        "Simplified effective sending window:",
        Math.min(receiveWindow, congestionWindow)
    );

    console.log(`
Flow control prevents a sender from overwhelming the receiver.

Congestion control attempts to prevent excessive traffic from overwhelming
the network.

These are different mechanisms even though both influence how much data TCP
can have in flight.
`);
}


// ============================================================================
// 13. PERFORMANCE
// ============================================================================

function demonstratePerformance() {
    printSection("13. PERFORMANCE CONSIDERATIONS");

    const messageSizes = [32, 128, 1024, 8192];

    for (const size of messageSizes) {
        console.log(`Payload size: ${size} bytes`);
    }

    console.log(`
Important variables include:
- Round-trip time
- Bandwidth
- Packet loss
- Queueing delay
- Congestion
- Number of connections
- Message size
- Serialization overhead
- Kernel socket buffers
- Application processing time

UDP can reduce transport-level machinery, but lower protocol overhead does
not automatically make an application faster. Reliability and congestion
behavior may need to be implemented at the application layer.
`);
}


// ============================================================================
// 14. SECURITY
// ============================================================================

function demonstrateSecurity() {
    printSection("14. SECURITY CONSIDERATIONS");

    console.log(`
TCP and UDP do not inherently encrypt application data.

Security-sensitive systems should consider:
- TLS or an authenticated secure transport
- Authentication
- Authorization
- Input validation
- Message-size limits
- Rate limiting
- Replay protection
- Resource limits
- Connection limits
- Timeout policies
- Safe error handling

Do not trust a source IP address as proof of user identity.
Do not parse unbounded network input into unbounded memory.
`);
}


// ============================================================================
// 15. MAIN
// ============================================================================

async function main() {
    demonstrateEndpoints();
    demonstrateThreeWayHandshake();
    demonstrateTcpByteStream();
    demonstrateFraming();

    const tcp = await startTcpServer();

    try {
        await runTcpClient(tcp.port);
    } finally {
        tcp.server.close();
    }

    const udp = await startUdpServer();

    try {
        const response = await sendUdpRequest(
            udp.port,
            "Hello UDP"
        );

        console.log("UDP client received:", response.toString());
    } finally {
        udp.server.close();
    }

    demonstrateReliableUdpDesign();
    demonstrateIntegrity();
    demonstrateTermination();
    demonstrateControlConcepts();
    demonstratePerformance();
    demonstrateSecurity();

    console.log("\nTCP and UDP study program complete.");
}

main().catch((error) => {
    console.error("Program failed:", error.message);
    process.exitCode = 1;
});
