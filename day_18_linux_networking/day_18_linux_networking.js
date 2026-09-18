#!/usr/bin/env node
"use strict";

/*
 * Linux Networking companion study program.
 *
 * Topics:
 *   - Network interfaces
 *   - IPv4 and IPv6 addresses
 *   - DNS
 *   - Routing
 *   - Ports
 *   - TCP and UDP
 *   - ip, ping, ss, and netstat
 *
 * This file is executable with Node.js on Linux:
 *
 *   node linux_networking.js
 *
 * It uses only Node.js built-in modules.
 */

const os = require("os");
const net = require("net");
const dgram = require("dgram");
const dns = require("dns");
const { execFile, spawn } = require("child_process");
const { promisify } = require("util");

const execFileAsync = promisify(execFile);


// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function section(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}

function subsection(title) {
    console.log(`\n--- ${title} ---`);
}

async function commandExists(command) {
    try {
        await execFileAsync("sh", ["-c", `command -v ${command}`]);
        return true;
    } catch {
        return false;
    }
}

async function runCommand(command, args = [], timeout = 5000) {
    try {
        const result = await execFileAsync(command, args, {
            timeout,
            maxBuffer: 1024 * 1024,
        });

        return {
            code: 0,
            stdout: result.stdout,
            stderr: result.stderr,
        };
    } catch (error) {
        return {
            code: typeof error.code === "number" ? error.code : 1,
            stdout: error.stdout || "",
            stderr: error.stderr || error.message || "",
        };
    }
}

async function printCommand(command, args = [], timeout = 5000) {
    console.log(`$ ${command} ${args.join(" ")}`.trim());

    const result = await runCommand(command, args, timeout);

    if (result.stdout.trim()) {
        console.log(result.stdout.trimEnd());
    }

    if (result.stderr.trim()) {
        console.log(`[stderr] ${result.stderr.trimEnd()}`);
    }

    if (result.code !== 0) {
        console.log(`[exit code: ${result.code}]`);
    }
}


// ---------------------------------------------------------------------------
// 1. Interfaces
// ---------------------------------------------------------------------------

function inspectInterfaces() {
    section("1. Network interfaces");

    /*
     * os.networkInterfaces() provides structured information directly from
     * Node.js. It is useful when an application needs local interface data
     * without parsing `ip addr`.
     */
    const interfaces = os.networkInterfaces();

    for (const [name, addresses] of Object.entries(interfaces)) {
        console.log(`\n${name}`);

        for (const address of addresses || []) {
            console.log(
                `  family=${address.family} ` +
                `address=${address.address} ` +
                `netmask=${address.netmask} ` +
                `internal=${address.internal} ` +
                `mac=${address.mac}`
            );
        }
    }
}


// ---------------------------------------------------------------------------
// 2. IP address and subnet concepts
// ---------------------------------------------------------------------------

function ipv4ToInteger(address) {
    const parts = address.split(".");

    if (parts.length !== 4) {
        throw new Error(`Invalid IPv4 address: ${address}`);
    }

    let result = 0;

    for (const part of parts) {
        if (!/^\d+$/.test(part)) {
            throw new Error(`Invalid IPv4 component: ${part}`);
        }

        const value = Number(part);

        if (value < 0 || value > 255) {
            throw new Error(`IPv4 component out of range: ${part}`);
        }

        result = result * 256 + value;
    }

    return result;
}

function integerToIpv4(value) {
    if (!Number.isInteger(value) || value < 0 || value > 0xffffffff) {
        throw new Error("IPv4 integer must be between 0 and 2^32 - 1.");
    }

    return [
        Math.floor(value / 2 ** 24) % 256,
        Math.floor(value / 2 ** 16) % 256,
        Math.floor(value / 2 ** 8) % 256,
        value % 256,
    ].join(".");
}

function subnetMaskFromPrefix(prefix) {
    if (!Number.isInteger(prefix) || prefix < 0 || prefix > 32) {
        throw new Error("IPv4 prefix must be between 0 and 32.");
    }

    if (prefix === 0) {
        return 0;
    }

    return (0xffffffff << (32 - prefix)) >>> 0;
}

function calculateSubnet(address, prefix) {
    const numericAddress = ipv4ToInteger(address);
    const mask = subnetMaskFromPrefix(prefix);
    const network = (numericAddress & mask) >>> 0;
    const broadcast = (network | (~mask >>> 0)) >>> 0;

    const hostCount = prefix >= 31
        ? 2 ** (32 - prefix)
        : Math.max(0, 2 ** (32 - prefix) - 2);

    return {
        address,
        prefix,
        netmask: integerToIpv4(mask),
        network: integerToIpv4(network),
        broadcast: integerToIpv4(broadcast),
        hostCount,
    };
}

function demonstrateSubnetting() {
    section("2. IPv4 addressing and subnetting");

    const examples = [
        ["192.168.1.25", 24],
        ["10.20.30.40", 16],
        ["172.16.10.50", 20],
        ["192.168.1.1", 32],
        ["10.0.0.1", 0],
    ];

    for (const [address, prefix] of examples) {
        try {
            const result = calculateSubnet(address, prefix);
            console.log(result);
        } catch (error) {
            console.log(error.message);
        }
    }

    subsection("Address validation edge cases");

    for (const address of [
        "127.0.0.1",
        "192.168.1.999",
        "10.0.0.1",
        "1.2.3",
        "01.02.03.04",
    ]) {
        try {
            console.log(`${address}: ${ipv4ToInteger(address)}`);
        } catch (error) {
            console.log(`${address}: invalid`);
        }
    }
}


// ---------------------------------------------------------------------------
// 3. DNS
// ---------------------------------------------------------------------------

async function demonstrateDns() {
    section("3. DNS and name resolution");

    console.log(
        "DNS translates names into resource records such as IPv4 A and IPv6 AAAA records."
    );

    const hostnames = [
        "localhost",
        "example.com",
        "invalid.invalid",
    ];

    for (const hostname of hostnames) {
        try {
            const result = await dns.promises.lookup(hostname, {
                all: true,
            });

            console.log(
                `${hostname}:`,
                result.map(item => `${item.address} (IPv${item.family})`).join(", ")
            );
        } catch (error) {
            console.log(`${hostname}: DNS lookup failed: ${error.code}`);
        }
    }

    subsection("DNS record types");

    console.log(`
A       IPv4 address
AAAA    IPv6 address
CNAME   Canonical-name alias
MX      Mail exchange
NS      Authoritative name server
TXT     Text data
PTR     Reverse DNS pointer
`);
}


// ---------------------------------------------------------------------------
// 4. Routing commands
// ---------------------------------------------------------------------------

async function inspectRouting() {
    section("4. Routing basics");

    console.log(`
Linux chooses an outgoing route using the routing table.

Useful commands:

  ip route
      Show IPv4 routes.

  ip -6 route
      Show IPv6 routes.

  ip route get <destination>
      Ask Linux which route it would select.

A default route is represented conceptually by 0.0.0.0/0 for IPv4 and ::/0
for IPv6. More specific prefixes normally win through longest-prefix matching.
`);

    if (await commandExists("ip")) {
        await printCommand("ip", ["route"]);
        await printCommand("ip", ["-6", "route"]);
        await printCommand("ip", ["route", "get", "127.0.0.1"]);
    } else {
        console.log("The ip command is not installed.");
    }
}


// ---------------------------------------------------------------------------
// 5. Longest-prefix routing simulation
// ---------------------------------------------------------------------------

function prefixMatches(address, network, prefix) {
    const addressNumber = ipv4ToInteger(address);
    const networkNumber = ipv4ToInteger(network);
    const mask = subnetMaskFromPrefix(prefix);

    return (addressNumber & mask) >>> 0 ===
        (networkNumber & mask) >>> 0;
}

function chooseRoute(routes, destination) {
    const matches = routes.filter(route =>
        prefixMatches(destination, route.network, route.prefix)
    );

    if (matches.length === 0) {
        return null;
    }

    return matches.sort((a, b) => {
        if (b.prefix !== a.prefix) {
            return b.prefix - a.prefix;
        }

        return a.metric - b.metric;
    })[0];
}

function demonstrateRoutingAlgorithm() {
    section("5. Longest-prefix matching");

    const routes = [
        {
            network: "0.0.0.0",
            prefix: 0,
            interface: "eth0",
            gateway: "192.168.1.1",
            metric: 100,
        },
        {
            network: "10.0.0.0",
            prefix: 8,
            interface: "vpn0",
            gateway: null,
            metric: 100,
        },
        {
            network: "10.20.0.0",
            prefix: 16,
            interface: "vpn1",
            gateway: null,
            metric: 100,
        },
        {
            network: "10.20.30.0",
            prefix: 24,
            interface: "vpn2",
            gateway: null,
            metric: 10,
        },
    ];

    for (const destination of [
        "8.8.8.8",
        "10.4.5.6",
        "10.20.5.6",
        "10.20.30.77",
    ]) {
        const route = chooseRoute(routes, destination);

        if (!route) {
            console.log(`${destination} -> no route`);
            continue;
        }

        console.log(
            `${destination} -> ${route.network}/${route.prefix} ` +
            `dev ${route.interface} ` +
            `gateway=${route.gateway || "direct"}`
        );
    }
}


// ---------------------------------------------------------------------------
// 6. ping
// ---------------------------------------------------------------------------

async function demonstratePing() {
    section("6. Connectivity testing with ping");

    console.log(`
ping normally tests IP reachability using ICMP Echo Request and Echo Reply.

A successful ping does not prove that an application port is available.
ICMP may be filtered while TCP or HTTPS remains reachable.
`);

    if (!(await commandExists("ping"))) {
        console.log("ping is not installed.");
        return;
    }

    // Loopback avoids depending on external Internet connectivity.
    await printCommand("ping", ["-c", "2", "127.0.0.1"]);

    console.log("\nFor external testing, an operator can use:");
    console.log("$ ping -c 4 example.com");
}


// ---------------------------------------------------------------------------
// 7. ss and netstat
// ---------------------------------------------------------------------------

async function inspectSockets() {
    section("7. Ports and socket inspection");

    console.log(`
ss is the preferred modern Linux socket-inspection command.

Common options:

  ss -tuln
      TCP/UDP listening sockets, numeric output.

  ss -tulpn
      Add process information where permissions allow it.

  ss -s
      Socket statistics.

netstat is an older utility from net-tools. It may not be installed on a
modern system.
`);

    if (await commandExists("ss")) {
        await printCommand("ss", ["-tuln"]);
        await printCommand("ss", ["-s"]);
    } else {
        console.log("ss is not installed.");
    }

    subsection("Legacy netstat");

    if (await commandExists("netstat")) {
        await printCommand("netstat", ["-tuln"]);
        await printCommand("netstat", ["-rn"]);
    } else {
        console.log("netstat is not installed.");
    }
}


// ---------------------------------------------------------------------------
// 8. TCP server case
// ---------------------------------------------------------------------------

function startTcpServer() {
    return new Promise((resolve, reject) => {
        /*
         * Binding to 127.0.0.1 makes this development server local-only.
         * Binding to 0.0.0.0 would expose it on all IPv4 interfaces.
         */
        const server = net.createServer(socket => {
            console.log(
                `TCP connection from ${socket.remoteAddress}:${socket.remotePort}`
            );

            socket.setEncoding("utf8");

            socket.on("data", data => {
                console.log(`Server received: ${JSON.stringify(data)}`);

                socket.write(`ACK:${data}`);

                socket.end();
            });

            socket.on("error", error => {
                console.log(`Socket error: ${error.message}`);
            });
        });

        server.once("error", reject);

        server.listen({
            host: "127.0.0.1",
            port: 0,
        }, () => {
            const address = server.address();

            console.log(
                `TCP server listening on ${address.address}:${address.port}`
            );

            resolve({
                server,
                port: address.port,
            });
        });
    });
}

function connectTcpClient(port) {
    return new Promise((resolve, reject) => {
        const client = net.createConnection({
            host: "127.0.0.1",
            port,
        });

        let response = "";

        client.setEncoding("utf8");

        client.on("connect", () => {
            client.write("hello-from-node");
        });

        client.on("data", data => {
            response += data;
        });

        client.on("end", () => {
            resolve(response);
        });

        client.on("error", reject);
    });
}

async function demonstrateTcp() {
    section("8. TCP server and client");

    let server;

    try {
        const started = await startTcpServer();
        server = started.server;

        const response = await connectTcpClient(started.port);

        console.log(`Client received: ${JSON.stringify(response)}`);

        await new Promise(resolve => server.close(resolve));

        console.log("TCP server closed.");
    } catch (error) {
        console.log(`TCP demonstration failed: ${error.message}`);

        if (server) {
            server.close();
        }
    }
}


// ---------------------------------------------------------------------------
// 9. UDP
// ---------------------------------------------------------------------------

function demonstrateUdp() {
    return new Promise((resolve) => {
        section("9. UDP datagram communication");

        const server = dgram.createSocket("udp4");
        const client = dgram.createSocket("udp4");

        let finished = false;

        function finish() {
            if (finished) {
                return;
            }

            finished = true;
            server.close();
            client.close();
            resolve();
        }

        server.on("message", (message, remote) => {
            console.log(
                `UDP server received ${JSON.stringify(message.toString())} ` +
                `from ${remote.address}:${remote.port}`
            );

            const response = Buffer.from(`ACK:${message.toString()}`);

            client.send(
                response,
                remote.port,
                remote.address,
                error => {
                    if (error) {
                        console.log(`UDP response failed: ${error.message}`);
                    }
                }
            );
        });

        server.on("error", error => {
            console.log(`UDP server error: ${error.message}`);
            finish();
        });

        client.on("error", error => {
            console.log(`UDP client error: ${error.message}`);
            finish();
        });

        server.bind(0, "127.0.0.1", () => {
            const address = server.address();

            console.log(
                `UDP server listening on ${address.address}:${address.port}`
            );

            client.send(
                Buffer.from("hello-udp"),
                address.port,
                "127.0.0.1",
                error => {
                    if (error) {
                        console.log(`UDP send failed: ${error.message}`);
                        finish();
                    }
                }
            );
        });

        client.on("message", message => {
            console.log(`UDP client received ${JSON.stringify(message.toString())}`);
            finish();
        });

        setTimeout(finish, 3000);
    });
}


// ---------------------------------------------------------------------------
// 10. Service and port concepts
// ---------------------------------------------------------------------------

function explainPorts() {
    section("10. Ports and services");

    const ports = {
        22: "SSH",
        25: "SMTP",
        53: "DNS",
        80: "HTTP",
        123: "NTP",
        443: "HTTPS",
        3306: "MySQL",
        5432: "PostgreSQL",
        6379: "Redis",
        8080: "Common application development port",
    };

    console.log("TCP and UDP have independent port spaces.");

    for (const [port, service] of Object.entries(ports)) {
        console.log(`${port.padStart(5)}  ${service}`);
    }

    console.log(`
A listening address matters:

  127.0.0.1:8080
      Usually local-host only.

  0.0.0.0:8080
      Listen on all IPv4 interfaces.

  [::]:8080
      IPv6 wildcard address, subject to operating-system dual-stack behavior.
`);
}


// ---------------------------------------------------------------------------
// 11. Node.js DNS and socket diagnostics
// ---------------------------------------------------------------------------

async function demonstrateSocketLookup() {
    section("11. Application-level socket lookup");

    try {
        const result = await dns.promises.lookup("localhost", {
            all: true,
        });

        for (const address of result) {
            console.log(
                `localhost -> ${address.address} IPv${address.family}`
            );
        }
    } catch (error) {
        console.log(`Lookup failed: ${error.message}`);
    }

    try {
        const result = await dns.promises.reverse("127.0.0.1");
        console.log(`Reverse lookup 127.0.0.1 -> ${result.join(", ")}`);
    } catch (error) {
        console.log(`Reverse lookup unavailable: ${error.code}`);
    }
}


// ---------------------------------------------------------------------------
// 12. Interface selection
// ---------------------------------------------------------------------------

async function demonstrateLocalInterfaceSelection() {
    section("12. Local address selection");

    /*
     * A UDP socket can be "connected" without establishing a UDP session.
     * The OS can then report the local address selected for that destination.
     */
    for (const destination of [
        ["127.0.0.1", 53],
        ["8.8.8.8", 53],
    ]) {
        const socket = dgram.createSocket("udp4");

        try {
            await new Promise((resolve, reject) => {
                socket.connect(destination[1], destination[0], error => {
                    if (error) {
                        reject(error);
                    } else {
                        resolve();
                    }
                });
            });

            const address = socket.address();

            console.log(
                `Destination ${destination[0]}:${destination[1]} ` +
                `selected local address ${address.address}`
            );
        } catch (error) {
            console.log(
                `Could not determine local address for ${destination[0]}: ` +
                `${error.message}`
            );
        } finally {
            socket.close();
        }
    }
}


// ---------------------------------------------------------------------------
// 13. Event-driven behavior
// ---------------------------------------------------------------------------

function demonstrateEventDrivenModel() {
    section("13. Event-driven networking in Node.js");

    console.log(`
Node.js networking APIs expose events such as:

  connect
  data
  end
  close
  error
  timeout

This model is important for network applications because network operations
complete asynchronously. Blocking the event loop with expensive synchronous
work can delay processing of unrelated connections and timers.
`);

    const emitter = new (require("events").EventEmitter)();

    emitter.on("packet", packet => {
        console.log(`Received application event: ${packet}`);
    });

    emitter.emit("packet", "simulated-network-message");
}


// ---------------------------------------------------------------------------
// 14. Validation
// ---------------------------------------------------------------------------

function validatePort(port) {
    return Number.isInteger(port) && port >= 0 && port <= 65535;
}

function validateHostname(hostname) {
    if (typeof hostname !== "string") {
        return false;
    }

    if (hostname.length === 0 || hostname.length > 253) {
        return false;
    }

    /*
     * This checks common hostname syntax. It does not prove that DNS can
     * resolve the hostname.
     */
    const labels = hostname.split(".");

    return labels.every(label =>
        label.length >= 1 &&
        label.length <= 63 &&
        /^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$/.test(label)
    );
}

function demonstrateValidation() {
    section("14. Network input validation");

    for (const port of [-1, 0, 22, 443, 65535, 65536, 80.5]) {
        console.log(
            `port=${port}: ${validatePort(port) ? "valid" : "invalid"}`
        );
    }

    for (const hostname of [
        "example.com",
        "localhost",
        "api.example.com",
        "-bad.example.com",
        "bad-.example.com",
        "",
    ]) {
        console.log(
            `${hostname || "<empty>"}: ` +
            `${validateHostname(hostname) ? "valid syntax" : "invalid syntax"}`
        );
    }
}


// ---------------------------------------------------------------------------
// 15. Troubleshooting
// ---------------------------------------------------------------------------

async function troubleshootingWorkflow() {
    section("15. Troubleshooting workflow");

    console.log(`
A useful diagnostic sequence is:

  1. Interface:
       ip -br link
       ip -br addr

  2. Route:
       ip route
       ip route get <destination>

  3. Connectivity:
       ping <destination>

  4. DNS:
       getent hosts <hostname>
       resolvectl query <hostname>

  5. Listening sockets:
       ss -tuln

  6. Application port:
       nc -vz <host> <port>
       curl -v http://<host>:<port>

Each test answers a different question. Avoid interpreting one layer as proof
that every other layer is functioning.
`);

    if (await commandExists("ip")) {
        await printCommand("ip", ["-br", "link"]);
        await printCommand("ip", ["-br", "addr"]);
    }

    if (await commandExists("ss")) {
        await printCommand("ss", ["-tuln"]);
    }
}


// ---------------------------------------------------------------------------
// 16. Main
// ---------------------------------------------------------------------------

async function main() {
    console.log("Linux Networking Study Program");
    console.log(`Node.js: ${process.version}`);
    console.log(`Platform: ${process.platform}`);
    console.log(`Architecture: ${process.arch}`);

    inspectInterfaces();
    demonstrateSubnetting();
    await demonstrateDns();
    await inspectRouting();
    demonstrateRoutingAlgorithm();
    await demonstratePing();
    await inspectSockets();
    explainPorts();
    await demonstrateTcp();
    await demonstrateUdp();
    await demonstrateSocketLookup();
    await demonstrateLocalInterfaceSelection();
    demonstrateEventDrivenModel();
    demonstrateValidation();
    await troubleshootingWorkflow();

    section("17. Production considerations");

    console.log(`
Performance:
  - Avoid unnecessary DNS resolution in high-frequency paths.
  - Use connection reuse where appropriate.
  - Use timeouts.
  - Avoid blocking the Node.js event loop.

Reliability:
  - Distinguish DNS errors from TCP connection errors.
  - Handle socket errors and connection termination.
  - Account for IPv4 and IPv6.

Security:
  - Bind development services to loopback when external access is unnecessary.
  - Validate untrusted hostnames, ports, and application data.
  - Use TLS for sensitive application traffic.
  - Do not expose administrative ports without appropriate controls.
  - Treat network input as untrusted.

The operating system remains responsible for routing packets and maintaining
interfaces. Node.js applications normally consume these capabilities through
the operating-system networking APIs.
`);

    section("18. End of program");
}

main().catch(error => {
    console.error(`Fatal error: ${error.message}`);
    process.exitCode = 1;
});
