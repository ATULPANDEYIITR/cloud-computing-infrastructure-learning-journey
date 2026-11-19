"use strict";

const net = require("node:net");
const crypto = require("node:crypto");
const { EventEmitter } = require("node:events");

const NetworkDriver = Object.freeze({
    BRIDGE: "bridge",
    HOST: "host",
    NONE: "none"
});

const NetworkState = Object.freeze({
    CREATED: "created",
    ACTIVE: "active",
    REMOVED: "removed"
});

class NetworkError extends Error {
    constructor(message) {
        super(message);
        this.name = "NetworkError";
    }
}

function validateIPv4(address) {
    if (typeof address !== "string" || !net.isIPv4(address)) {
        throw new NetworkError(`Invalid IPv4 address: ${address}`);
    }
    return address;
}

function validateCIDR(cidr) {
    if (typeof cidr !== "string") {
        throw new NetworkError("CIDR must be a string.");
    }

    const parts = cidr.split("/");
    if (parts.length !== 2 || !net.isIPv4(parts[0])) {
        throw new NetworkError(`Invalid IPv4 CIDR: ${cidr}`);
    }

    const prefix = Number(parts[1]);

    if (!Number.isInteger(prefix) || prefix < 0 || prefix > 32) {
        throw new NetworkError(`Invalid CIDR prefix: ${cidr}`);
    }

    return { address: parts[0], prefix };
}

function ipv4ToInteger(address) {
    return address.split(".")
        .reduce((result, octet) => ((result << 8) | Number(octet)) >>> 0, 0);
}

function integerToIPv4(value) {
    return [
        (value >>> 24) & 255,
        (value >>> 16) & 255,
        (value >>> 8) & 255,
        value & 255
    ].join(".");
}

function isInSubnet(address, cidr) {
    const parsed = validateCIDR(cidr);
    const mask = parsed.prefix === 0
        ? 0
        : (0xFFFFFFFF << (32 - parsed.prefix)) >>> 0;

    return (
        (ipv4ToInteger(address) & mask) ===
        (ipv4ToInteger(parsed.address) & mask)
    );
}

class Container {
    constructor({ name, image, networkMode = NetworkDriver.BRIDGE }) {
        if (!name || !/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}$/.test(name)) {
            throw new NetworkError("Invalid container name.");
        }

        if (!image || typeof image !== "string") {
            throw new NetworkError("Container image is required.");
        }

        if (!Object.values(NetworkDriver).includes(networkMode)) {
            throw new NetworkError("Unsupported network mode.");
        }

        this.id = crypto.randomUUID();
        this.name = name;
        this.image = image;
        this.networkMode = networkMode;
        this.networks = new Map();
        this.state = "running";
    }
}

class DockerNetwork {
    constructor({ name, subnet, driver = NetworkDriver.BRIDGE, internal = false }) {
        if (!name || !/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}$/.test(name)) {
            throw new NetworkError("Invalid network name.");
        }

        if (!Object.values(NetworkDriver).includes(driver)) {
            throw new NetworkError("Unsupported network driver.");
        }

        if (driver === NetworkDriver.BRIDGE && !subnet) {
            throw new NetworkError("Bridge networks require a subnet.");
        }

        if (driver === NetworkDriver.HOST && subnet) {
            throw new NetworkError("Host networks do not allocate a container subnet.");
        }

        this.id = crypto.randomUUID();
        this.name = name;
        this.driver = driver;
        this.subnet = subnet ? validateCIDR(subnet) : null;
        this.cidr = subnet || null;
        this.internal = Boolean(internal);
        this.state = NetworkState.CREATED;
        this.containers = new Map();
        this.nextHost = 2;

        if (driver === NetworkDriver.BRIDGE) {
            this.activate();
        }
    }

    activate() {
        if (this.state === NetworkState.REMOVED) {
            throw new NetworkError("A removed network cannot be activated.");
        }

        this.state = NetworkState.ACTIVE;
    }

    allocateIP() {
        if (this.driver !== NetworkDriver.BRIDGE) {
            return null;
        }

        const { address, prefix } = this.subnet;

        if (prefix >= 31) {
            throw new NetworkError("Subnet has insufficient host capacity.");
        }

        const networkAddress = ipv4ToInteger(address);
        const mask = (0xFFFFFFFF << (32 - prefix)) >>> 0;
        const networkBase = (networkAddress & mask) >>> 0;
        const broadcast = (networkBase | (~mask >>> 0)) >>> 0;
        const candidate = networkBase + this.nextHost;

        if (candidate >= broadcast) {
            throw new NetworkError(`No available IP addresses in ${this.name}.`);
        }

        this.nextHost++;

        return integerToIPv4(candidate >>> 0);
    }

    connect(container, aliases = []) {
        if (this.state !== NetworkState.ACTIVE) {
            throw new NetworkError("Network is not active.");
        }

        if (!(container instanceof Container)) {
            throw new NetworkError("Invalid container.");
        }

        if (container.state !== "running") {
            throw new NetworkError("Container is not running.");
        }

        if (this.driver === NetworkDriver.HOST) {
            throw new NetworkError("Host networking does not support bridge-style attachment.");
        }

        if (this.driver === NetworkDriver.NONE) {
            throw new NetworkError("No-network mode cannot accept attachments.");
        }

        if (container.networkMode === NetworkDriver.HOST ||
            container.networkMode === NetworkDriver.NONE) {
            throw new NetworkError("Container network mode conflicts with bridge attachment.");
        }

        if (this.containers.has(container.id)) {
            throw new NetworkError("Container is already connected.");
        }

        const normalizedAliases = new Set([container.name]);

        for (const alias of aliases) {
            if (typeof alias !== "string" ||
                !/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}$/.test(alias)) {
                throw new NetworkError(`Invalid network alias: ${alias}`);
            }
            normalizedAliases.add(alias);
        }

        const ip = this.allocateIP();

        const attachment = {
            container,
            ip,
            aliases: normalizedAliases
        };

        this.containers.set(container.id, attachment);
        container.networks.set(this.id, attachment);

        return ip;
    }

    disconnect(container) {
        const attachment = this.containers.get(container.id);

        if (!attachment) {
            throw new NetworkError("Container is not connected to this network.");
        }

        this.containers.delete(container.id);
        container.networks.delete(this.id);
    }

    resolve(name) {
        for (const attachment of this.containers.values()) {
            if (attachment.aliases.has(name)) {
                return attachment.ip;
            }
        }

        throw new NetworkError(`DNS name not found: ${name}`);
    }

    remove() {
        if (this.containers.size > 0) {
            throw new NetworkError("Disconnect all containers before removing the network.");
        }

        this.state = NetworkState.REMOVED;
    }

    inspect() {
        return {
            id: this.id,
            name: this.name,
            driver: this.driver,
            subnet: this.cidr,
            internal: this.internal,
            state: this.state,
            containers: [...this.containers.values()].map(item => ({
                name: item.container.name,
                ip: item.ip,
                aliases: [...item.aliases]
            }))
        };
    }
}

class DockerHost {
    constructor() {
        this.networks = new Map();
        this.containers = new Map();
        this.events = new EventEmitter();

        // Default bridge represents the default Docker bridge conceptually.
        this.createNetwork({
            name: "bridge",
            subnet: "172.20.0.0/24"
        });
    }

    createNetwork(options) {
        if (this.networks.has(options.name)) {
            throw new NetworkError(`Network already exists: ${options.name}`);
        }

        const network = new DockerNetwork(options);

        if (network.driver === NetworkDriver.BRIDGE) {
            for (const existing of this.networks.values()) {
                if (
                    existing.driver === NetworkDriver.BRIDGE &&
                    existing.state === NetworkState.ACTIVE &&
                    this.subnetsOverlap(existing.subnet, network.subnet)
                ) {
                    throw new NetworkError(
                        `Subnet ${network.cidr} overlaps with ${existing.cidr}.`
                    );
                }
            }
        }

        this.networks.set(network.name, network);
        this.events.emit("network.created", network.inspect());

        return network;
    }

    subnetsOverlap(first, second) {
        const firstPrefix = first.prefix;
        const secondPrefix = second.prefix;

        const firstMask = firstPrefix === 0
            ? 0
            : (0xFFFFFFFF << (32 - firstPrefix)) >>> 0;

        const secondMask = secondPrefix === 0
            ? 0
            : (0xFFFFFFFF << (32 - secondPrefix)) >>> 0;

        const firstNetwork =
            (ipv4ToInteger(first.address) & firstMask) >>> 0;

        const secondNetwork =
            (ipv4ToInteger(second.address) & secondMask) >>> 0;

        return (
            (firstNetwork & secondMask) === secondNetwork ||
            (secondNetwork & firstMask) === firstNetwork
        );
    }

    createContainer(options) {
        if (this.containers.has(options.name)) {
            throw new NetworkError(`Container already exists: ${options.name}`);
        }

        const container = new Container(options);

        this.containers.set(container.name, container);

        this.events.emit("container.created", {
            id: container.id,
            name: container.name,
            image: container.image
        });

        return container;
    }

    connect(containerName, networkName, aliases = []) {
        const container = this.containers.get(containerName);
        const network = this.networks.get(networkName);

        if (!container || !network) {
            throw new NetworkError("Container or network not found.");
        }

        const ip = network.connect(container, aliases);

        this.events.emit("container.connected", {
            container: containerName,
            network: networkName,
            ip
        });

        return ip;
    }

    disconnect(containerName, networkName) {
        const container = this.containers.get(containerName);
        const network = this.networks.get(networkName);

        if (!container || !network) {
            throw new NetworkError("Container or network not found.");
        }

        network.disconnect(container);

        this.events.emit("container.disconnected", {
            container: containerName,
            network: networkName
        });
    }

    removeNetwork(name) {
        const network = this.networks.get(name);

        if (!network) {
            throw new NetworkError("Network not found.");
        }

        network.remove();
        this.networks.delete(name);

        this.events.emit("network.removed", { name });
    }

    inspectNetwork(name) {
        const network = this.networks.get(name);

        if (!network) {
            throw new NetworkError("Network not found.");
        }

        return network.inspect();
    }

    canCommunicate(sourceName, targetName, networkName) {
        const source = this.containers.get(sourceName);
        const target = this.containers.get(targetName);
        const network = this.networks.get(networkName);

        if (!source || !target || !network) {
            throw new NetworkError("Communication endpoint or network not found.");
        }

        if (network.internal && network.driver === NetworkDriver.BRIDGE) {
            // Internal networks provide isolated connectivity without external routing.
        }

        return (
            network.containers.has(source.id) &&
            network.containers.has(target.id) &&
            source.state === "running" &&
            target.state === "running"
        );
    }
}

function runDemonstration() {
    const host = new DockerHost();

    host.events.on("network.created", event => {
        console.log(`[EVENT] Network created: ${event.name}`);
    });

    host.events.on("container.connected", event => {
        console.log(
            `[EVENT] ${event.container} connected to ${event.network}: ${event.ip}`
        );
    });

    // Create an isolated application network.
    const appNetwork = host.createNetwork({
        name: "application-network",
        subnet: "10.10.0.0/24",
        driver: NetworkDriver.BRIDGE,
        internal: true
    });

    // Create independent application containers.
    const api = host.createContainer({
        name: "api-server",
        image: "node:22-alpine"
    });

    const database = host.createContainer({
        name: "postgres-db",
        image: "postgres:17-alpine"
    });

    const frontend = host.createContainer({
        name: "frontend",
        image: "nginx:alpine"
    });

    host.connect("api-server", "application-network", ["api"]);
    host.connect("postgres-db", "application-network", ["database", "db"]);
    host.connect("frontend", "application-network", ["web"]);

    console.log("\n--- Network inspection ---");
    console.log(JSON.stringify(host.inspectNetwork("application-network"), null, 2));

    console.log("\n--- Container DNS resolution ---");
    console.log("database ->", appNetwork.resolve("database"));
    console.log("api ->", appNetwork.resolve("api"));

    console.log("\n--- Communication evaluation ---");
    console.log(
        "API to database:",
        host.canCommunicate("api-server", "postgres-db", "application-network")
    );

    console.log(
        "Frontend to database:",
        host.canCommunicate("frontend", "postgres-db", "application-network")
    );

    console.log("\n--- Host and none networking concepts ---");
    const hostContainer = host.createContainer({
        name: "host-monitor",
        image: "alpine:latest",
        networkMode: NetworkDriver.HOST
    });

    const isolatedContainer = host.createContainer({
        name: "isolated-task",
        image: "alpine:latest",
        networkMode: NetworkDriver.NONE
    });

    console.log("Host-mode container:", hostContainer.name);
    console.log("None-mode container:", isolatedContainer.name);

    console.log("\n--- Disconnect and cleanup ---");

    host.disconnect("frontend", "application-network");
    host.disconnect("postgres-db", "application-network");
    host.disconnect("api-server", "application-network");

    host.removeNetwork("application-network");

    console.log("Application network removed successfully.");

    // Invalid operations demonstrate controlled failure handling.
    try {
        host.createNetwork({
            name: "overlapping-network",
            subnet: "10.10.0.128/25"
        });
    } catch (error) {
        console.log("[EXPECTED ERROR]", error.message);
    }

    try {
        validateIPv4("999.10.10.1");
    } catch (error) {
        console.log("[EXPECTED ERROR]", error.message);
    }
}

function runTests() {
    console.log("\n--- Validation tests ---");

    console.assert(net.isIPv4("192.168.1.10"));
    console.assert(!net.isIPv4("999.999.999.999"));

    console.assert(
        isInSubnet("10.10.0.15", "10.10.0.0/24")
    );

    console.assert(
        !isInSubnet("10.11.0.15", "10.10.0.0/24")
    );

    const network = new DockerNetwork({
        name: "test-network",
        subnet: "192.168.50.0/24"
    });

    const container = new Container({
        name: "test-container",
        image: "alpine:latest"
    });

    const ip = network.connect(container);

    console.assert(ip === "192.168.50.2");
    console.assert(network.resolve("test-container") === ip);

    network.disconnect(container);
    network.remove();

    console.log("All validation tests passed.");
}

if (require.main === module) {
    try {
        runDemonstration();
        runTests();
    } catch (error) {
        console.error(`[FATAL] ${error.name}: ${error.message}`);
        process.exitCode = 1;
    }
}

module.exports = {
    DockerHost,
    DockerNetwork,
    Container,
    NetworkDriver,
    NetworkState,
    NetworkError,
    validateIPv4,
    validateCIDR,
    isInSubnet
};
