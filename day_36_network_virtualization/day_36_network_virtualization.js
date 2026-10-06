'use strict';

/*
 * Network Virtualization Event Lab
 *
 * This Node.js program models network virtualization from an operational
 * perspective. It focuses on event-driven control, virtual switches, logical
 * segments, overlay encapsulation, SDN policy, and asynchronous state changes.
 *
 * Run with:
 *   node network_virtualization.js
 */

const EventEmitter = require('node:events');

function assert(condition, message) {
    if (!condition) {
        throw new Error(message);
    }
}

function normalizeMac(mac) {
    const value = String(mac).toLowerCase();

    if (!/^([0-9a-f]{2}:){5}[0-9a-f]{2}$/.test(value)) {
        throw new Error(`Invalid MAC address: ${mac}`);
    }

    return value;
}

function ipToInteger(ip) {
    const parts = ip.split('.').map(Number);

    if (
        parts.length !== 4 ||
        parts.some(
            part => !Number.isInteger(part) || part < 0 || part > 255
        )
    ) {
        throw new Error(`Invalid IPv4 address: ${ip}`);
    }

    return (
        ((parts[0] << 24) >>> 0) |
        ((parts[1] << 16) >>> 0) |
        ((parts[2] << 8) >>> 0) |
        parts[3]
    ) >>> 0;
}

function ipInCidr(ip, cidr) {
    const [network, prefixText] = cidr.split('/');
    const prefix = Number(prefixText);

    if (!Number.isInteger(prefix) || prefix < 0 || prefix > 32) {
        throw new Error(`Invalid CIDR prefix: ${cidr}`);
    }

    const address = ipToInteger(ip);
    const networkAddress = ipToInteger(network);

    if (prefix === 0) {
        return true;
    }

    const mask = (0xffffffff << (32 - prefix)) >>> 0;

    return (address & mask) === (networkAddress & mask);
}

class VirtualNetwork {
    constructor({ name, cidr, vlanId, vni, gateway, isolated = false }) {
        if (!name || !cidr) {
            throw new Error('A virtual network requires a name and CIDR');
        }

        if (!Number.isInteger(vlanId) || vlanId < 1 || vlanId > 4094) {
            throw new Error(`Invalid VLAN ID: ${vlanId}`);
        }

        if (!Number.isInteger(vni) || vni < 1 || vni > 16777215) {
            throw new Error(`Invalid VNI: ${vni}`);
        }

        this.name = name;
        this.cidr = cidr;
        this.vlanId = vlanId;
        this.vni = vni;
        this.gateway = gateway;
        this.isolated = isolated;
    }

    contains(ip) {
        return ipInCidr(ip, this.cidr);
    }
}

class VirtualNIC {
    constructor({ name, mac, ip, network }) {
        this.name = name;
        this.mac = normalizeMac(mac);
        this.ip = ip;
        this.network = network;
        this.enabled = true;
    }
}

class VirtualMachine {
    constructor(name) {
        this.name = name;
        this.nics = new Map();
    }

    attachNIC(nic) {
        assert(!this.nics.has(nic.name), `NIC already exists: ${nic.name}`);
        this.nics.set(nic.name, nic);
    }

    getNIC(name) {
        const nic = this.nics.get(name);
        assert(nic, `NIC not found: ${name}`);
        return nic;
    }
}

class EthernetFrame {
    constructor({
        sourceMac,
        destinationMac,
        sourceIp,
        destinationIp,
        payload,
        vlanId = null
    }) {
        this.sourceMac = normalizeMac(sourceMac);
        this.destinationMac = normalizeMac(destinationMac);
        this.sourceIp = sourceIp;
        this.destinationIp = destinationIp;
        this.payload = payload;
        this.vlanId = vlanId;
    }

    get byteLength() {
        return Buffer.byteLength(this.payload, 'utf8') + 14;
    }
}

class VirtualSwitch extends EventEmitter {
    constructor(name) {
        super();

        this.name = name;
        this.ports = new Map();
        this.macTable = new Map();
        this.statistics = {
            received: 0,
            forwarded: 0,
            flooded: 0,
            dropped: 0
        };
    }

    addPort(name, nic = null) {
        assert(!this.ports.has(name), `Port already exists: ${name}`);

        this.ports.set(name, {
            name,
            nic,
            enabled: true
        });
    }

    setPortState(name, enabled) {
        const port = this.ports.get(name);
        assert(port, `Unknown port: ${name}`);

        port.enabled = enabled;

        this.emit('portStateChanged', {
            switch: this.name,
            port: name,
            enabled
        });
    }

    receive(frame, ingressPort) {
        this.statistics.received++;

        const ingress = this.ports.get(ingressPort);

        if (!ingress || !ingress.enabled) {
            this.statistics.dropped++;
            this.emit('packetDropped', {
                reason: 'disabled-or-missing-ingress',
                switch: this.name,
                ingressPort
            });
            return [];
        }

        // MAC learning is a data-plane behavior. The switch learns where the
        // source endpoint is located from the incoming Ethernet frame.
        this.macTable.set(frame.sourceMac, ingressPort);

        const destinationPort = this.macTable.get(frame.destinationMac);

        if (destinationPort) {
            if (destinationPort === ingressPort) {
                return [];
            }

            const port = this.ports.get(destinationPort);

            if (!port || !port.enabled) {
                this.statistics.dropped++;
                this.emit('packetDropped', {
                    reason: 'known-destination-port-disabled',
                    switch: this.name,
                    destinationPort
                });
                return [];
            }

            this.statistics.forwarded++;
            this.emit('forwarded', {
                switch: this.name,
                from: ingressPort,
                to: destinationPort,
                frame
            });

            return [destinationPort];
        }

        const floodTargets = [];

        for (const [portName, port] of this.ports) {
            if (portName !== ingressPort && port.enabled) {
                floodTargets.push(portName);
            }
        }

        this.statistics.flooded += floodTargets.length;

        this.emit('flooded', {
            switch: this.name,
            from: ingressPort,
            targets: floodTargets,
            frame
        });

        return floodTargets;
    }

    showMacTable() {
        return Object.fromEntries(this.macTable.entries());
    }
}

class OverlayTunnel {
    constructor({ name, localEndpoint, remoteEndpoint, vni }) {
        if (!Number.isInteger(vni) || vni < 1 || vni > 16777215) {
            throw new Error(`Invalid VNI: ${vni}`);
        }

        this.name = name;
        this.localEndpoint = localEndpoint;
        this.remoteEndpoint = remoteEndpoint;
        this.vni = vni;
        this.up = true;
    }

    encapsulate(frame) {
        assert(this.up, `Tunnel ${this.name} is down`);

        return {
            outerHeader: {
                source: this.localEndpoint,
                destination: this.remoteEndpoint,
                protocol: 'UDP',
                destinationPort: 4789
            },
            vxlanHeader: {
                vni: this.vni
            },
            innerFrame: frame
        };
    }

    decapsulate(packet) {
        assert(this.up, `Tunnel ${this.name} is down`);
        assert(
            packet.vxlanHeader.vni === this.vni,
            `VNI mismatch on ${this.name}`
        );

        return packet.innerFrame;
    }
}

class SDNController extends EventEmitter {
    constructor(name) {
        super();

        this.name = name;
        this.networks = new Map();
        this.switches = new Map();
        this.policies = new Map();
    }

    registerNetwork(network) {
        assert(
            !this.networks.has(network.name),
            `Network already registered: ${network.name}`
        );

        this.networks.set(network.name, network);
    }

    registerSwitch(vswitch) {
        this.switches.set(vswitch.name, vswitch);

        vswitch.on('portStateChanged', event => {
            this.emit('topologyChanged', event);
        });

        vswitch.on('packetDropped', event => {
            this.emit('dataPlaneDrop', event);
        });
    }

    setPolicy(source, destination, action) {
        assert(this.networks.has(source), `Unknown source network: ${source}`);
        assert(
            this.networks.has(destination),
            `Unknown destination network: ${destination}`
        );
        assert(
            action === 'ALLOW' || action === 'DENY',
            `Unsupported policy action: ${action}`
        );

        this.policies.set(`${source}->${destination}`, action);
    }

    evaluatePolicy(source, destination) {
        return this.policies.get(`${source}->${destination}`) ?? 'DENY';
    }

    async reconcile() {
        /*
         * In a real SDN system, reconciliation would communicate desired
         * forwarding state to network devices through a controller protocol.
         * The asynchronous delay models that control-plane operation.
         */
        await new Promise(resolve => setTimeout(resolve, 25));

        const snapshot = [];

        for (const [name, vswitch] of this.switches) {
            snapshot.push({
                switch: name,
                ports: [...vswitch.ports.keys()],
                learnedMacs: vswitch.macTable.size
            });
        }

        this.emit('reconciled', snapshot);
        return snapshot;
    }
}

class VirtualRouter {
    constructor(controller) {
        this.controller = controller;
        this.routingTable = [];
    }

    addRoute(cidr, networkName) {
        assert(
            this.controller.networks.has(networkName),
            `Unknown network: ${networkName}`
        );

        this.routingTable.push({
            cidr,
            networkName
        });
    }

    findDestinationNetwork(ip) {
        const matches = this.routingTable.filter(route =>
            ipInCidr(ip, route.cidr)
        );

        return matches.length
            ? matches[matches.length - 1].networkName
            : null;
    }

    route(frame, sourceNetwork) {
        const destinationNetwork = this.findDestinationNetwork(
            frame.destinationIp
        );

        if (!destinationNetwork) {
            return {
                allowed: false,
                reason: 'No route'
            };
        }

        const action = this.controller.evaluatePolicy(
            sourceNetwork,
            destinationNetwork
        );

        if (action !== 'ALLOW') {
            return {
                allowed: false,
                reason: `Policy ${action}`
            };
        }

        return {
            allowed: true,
            destinationNetwork
        };
    }
}

function sleep(milliseconds) {
    return new Promise(resolve => setTimeout(resolve, milliseconds));
}

async function demonstrateVirtualSwitching(lab) {
    console.log('\n=== Virtual switch learning ===');

    const web = lab.web.getNIC('eth0');
    const app = lab.app.getNIC('eth0');

    const firstFrame = new EthernetFrame({
        sourceMac: web.mac,
        destinationMac: app.mac,
        sourceIp: web.ip,
        destinationIp: app.ip,
        payload: 'GET /orders',
        vlanId: lab.networks.get('frontend').vlanId
    });

    const firstDecision = lab.switch.receive(firstFrame, 'web-port');

    console.log('Unknown destination causes forwarding to:', firstDecision);

    const response = new EthernetFrame({
        sourceMac: app.mac,
        destinationMac: web.mac,
        sourceIp: app.ip,
        destinationIp: web.ip,
        payload: 'HTTP 200',
        vlanId: lab.networks.get('frontend').vlanId
    });

    const secondDecision = lab.switch.receive(response, 'app-port');

    console.log('Learned destination causes forwarding to:', secondDecision);
    console.log('MAC table:', lab.switch.showMacTable());
}

async function demonstrateOverlay(lab) {
    console.log('\n=== Overlay network ===');

    const web = lab.web.getNIC('eth0');
    const app = lab.app.getNIC('eth0');

    const frame = new EthernetFrame({
        sourceMac: web.mac,
        destinationMac: app.mac,
        sourceIp: web.ip,
        destinationIp: app.ip,
        payload: 'Tenant traffic'
    });

    const packet = lab.tunnel.encapsulate(frame);

    console.log(
        `Outer transport: ${packet.outerHeader.source} -> ` +
        `${packet.outerHeader.destination}`
    );
    console.log(`VXLAN VNI: ${packet.vxlanHeader.vni}`);

    const recovered = lab.tunnel.decapsulate(packet);

    console.log(
        `Recovered inner frame: ${recovered.sourceIp} -> ` +
        `${recovered.destinationIp}`
    );
}

async function demonstrateSDNPolicy(lab) {
    console.log('\n=== SDN control-plane policy ===');

    const web = lab.web.getNIC('eth0');
    const database = lab.database.getNIC('eth0');

    const frame = new EthernetFrame({
        sourceMac: web.mac,
        destinationMac: database.mac,
        sourceIp: web.ip,
        destinationIp: database.ip,
        payload: 'database request'
    });

    const result = lab.router.route(frame, 'frontend');

    console.log('Frontend -> database:', result);

    const allowedFrame = new EthernetFrame({
        sourceMac: lab.app.getNIC('eth0').mac,
        destinationMac: database.mac,
        sourceIp: lab.app.getNIC('eth0').ip,
        destinationIp: database.ip,
        payload: 'database request'
    });

    console.log(
        'Backend -> database:',
        lab.router.route(allowedFrame, 'backend')
    );
}

async function demonstrateFailureAndReconciliation(lab) {
    console.log('\n=== Event-driven failure handling ===');

    const web = lab.web.getNIC('eth0');
    const app = lab.app.getNIC('eth0');

    lab.switch.setPortState('app-port', false);

    const frame = new EthernetFrame({
        sourceMac: web.mac,
        destinationMac: app.mac,
        sourceIp: web.ip,
        destinationIp: app.ip,
        payload: 'request during outage'
    });

    lab.switch.receive(frame, 'web-port');

    await lab.controller.reconcile();

    lab.switch.setPortState('app-port', true);

    await sleep(10);

    console.log('Port restored and topology reconciled.');
}

async function main() {
    const controller = new SDNController('controller-01');

    const frontend = new VirtualNetwork({
        name: 'frontend',
        cidr: '10.10.10.0/24',
        vlanId: 110,
        vni: 5001,
        gateway: '10.10.10.1'
    });

    const backend = new VirtualNetwork({
        name: 'backend',
        cidr: '10.10.20.0/24',
        vlanId: 120,
        vni: 5002,
        gateway: '10.10.20.1'
    });

    const database = new VirtualNetwork({
        name: 'database',
        cidr: '10.10.30.0/24',
        vlanId: 130,
        vni: 5003,
        gateway: '10.10.30.1',
        isolated: true
    });

    controller.registerNetwork(frontend);
    controller.registerNetwork(backend);
    controller.registerNetwork(database);

    controller.setPolicy('frontend', 'frontend', 'ALLOW');
    controller.setPolicy('backend', 'backend', 'ALLOW');
    controller.setPolicy('database', 'database', 'ALLOW');
    controller.setPolicy('frontend', 'backend', 'ALLOW');
    controller.setPolicy('backend', 'frontend', 'ALLOW');
    controller.setPolicy('backend', 'database', 'ALLOW');
    controller.setPolicy('database', 'backend', 'ALLOW');
    controller.setPolicy('frontend', 'database', 'DENY');
    controller.setPolicy('database', 'frontend', 'DENY');

    const vswitch = new VirtualSwitch('vswitch-01');

    const web = new VirtualMachine('web-01');
    web.attachNIC(
        new VirtualNIC({
            name: 'eth0',
            mac: '02:00:00:00:10:01',
            ip: '10.10.10.10',
            network: 'frontend'
        })
    );

    const app = new VirtualMachine('app-01');
    app.attachNIC(
        new VirtualNIC({
            name: 'eth0',
            mac: '02:00:00:00:20:01',
            ip: '10.10.20.10',
            network: 'backend'
        })
    );

    const databaseVM = new VirtualMachine('db-01');
    databaseVM.attachNIC(
        new VirtualNIC({
            name: 'eth0',
            mac: '02:00:00:00:30:01',
            ip: '10.10.30.10',
            network: 'database'
        })
    );

    vswitch.addPort('web-port', web.getNIC('eth0'));
    vswitch.addPort('app-port', app.getNIC('eth0'));
    vswitch.addPort('uplink-port');

    controller.registerSwitch(vswitch);

    controller.on('topologyChanged', event => {
        console.log(
            `Controller event: port ${event.port} on ${event.switch} ` +
            `is ${event.enabled ? 'UP' : 'DOWN'}`
        );
    });

    controller.on('dataPlaneDrop', event => {
        console.log(
            `Controller observed data-plane drop: ${event.reason}`
        );
    });

    const router = new VirtualRouter(controller);
    router.addRoute('10.10.10.0/24', 'frontend');
    router.addRoute('10.10.20.0/24', 'backend');
    router.addRoute('10.10.30.0/24', 'database');

    const tunnel = new OverlayTunnel({
        name: 'vxlan-frontend-backend',
        localEndpoint: '192.0.2.10',
        remoteEndpoint: '192.0.2.20',
        vni: 5001
    });

    const lab = {
        controller,
        networks: controller.networks,
        switch: vswitch,
        router,
        tunnel,
        web,
        app,
        database: databaseVM
    };

    console.log('NETWORK VIRTUALIZATION EVENT LAB');
    console.log(
        'Virtual networks:',
        [...controller.networks.values()].map(network => ({
            name: network.name,
            vlan: network.vlanId,
            vni: network.vni,
            cidr: network.cidr
        }))
    );

    await demonstrateVirtualSwitching(lab);
    await demonstrateOverlay(lab);
    await demonstrateSDNPolicy(lab);
    await demonstrateFailureAndReconciliation(lab);

    console.log('\n=== Final switch statistics ===');
    console.log(vswitch.statistics);
}

main().catch(error => {
    console.error('Fatal network-lab error:', error.message);
    process.exitCode = 1;
});
