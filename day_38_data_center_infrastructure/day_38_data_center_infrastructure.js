"use strict";

/*
 * Data Center Infrastructure Model
 *
 * This Node.js program models physical infrastructure rather than application
 * software. It focuses on rack placement, electrical capacity, cooling load,
 * network-path redundancy, and failure-domain analysis.
 *
 * Run with:
 *   node datacenter_infrastructure.js
 */

class CapacityError extends Error {
  constructor(message) {
    super(message);
    this.name = "CapacityError";
  }
}

class InfrastructureValidationError extends Error {
  constructor(message) {
    super(message);
    this.name = "InfrastructureValidationError";
  }
}

class Rack {
  constructor(id, capacityU = 42, powerCapacityKW = 10) {
    if (capacityU <= 0 || powerCapacityKW <= 0) {
      throw new InfrastructureValidationError(
        "Rack dimensions and power capacity must be positive."
      );
    }

    this.id = id;
    this.capacityU = capacityU;
    this.powerCapacityKW = powerCapacityKW;
    this.servers = [];
  }

  get usedU() {
    return this.servers.length;
  }

  get usedPowerKW() {
    return this.servers.reduce((sum, server) => sum + server.powerKW, 0);
  }

  canInstall(server) {
    return (
      this.usedU < this.capacityU &&
      this.usedPowerKW + server.powerKW <= this.powerCapacityKW
    );
  }

  install(server) {
    if (!this.canInstall(server)) {
      throw new CapacityError(
        `Rack ${this.id} cannot accommodate ${server.name}.`
      );
    }

    this.servers.push(server);
  }
}

class Server {
  constructor({
    name,
    rackId,
    powerKW,
    networkPorts = 2,
    powerPaths = ["A", "B"],
    role
  }) {
    if (!name || !rackId || !role) {
      throw new InfrastructureValidationError(
        "Server name, rack, and role are required."
      );
    }

    if (powerKW <= 0) {
      throw new InfrastructureValidationError(
        `Server ${name} must have positive power consumption.`
      );
    }

    if (networkPorts < 1) {
      throw new InfrastructureValidationError(
        `Server ${name} must have at least one network connection.`
      );
    }

    this.name = name;
    this.rackId = rackId;
    this.powerKW = powerKW;
    this.networkPorts = networkPorts;
    this.powerPaths = new Set(powerPaths);
    this.role = role;
    this.state = "RUNNING";
  }
}

class PowerSystem {
  constructor(feedCapacityKW) {
    this.feeds = {
      A: { capacityKW: feedCapacityKW, loadKW: 0, available: true },
      B: { capacityKW: feedCapacityKW, loadKW: 0, available: true }
    };
  }

  reserve(path, powerKW) {
    const feed = this.feeds[path];

    if (!feed) {
      throw new InfrastructureValidationError(`Unknown power path ${path}.`);
    }

    if (!feed.available) {
      throw new CapacityError(`Power path ${path} is unavailable.`);
    }

    if (feed.loadKW + powerKW > feed.capacityKW) {
      throw new CapacityError(
        `Power path ${path} would exceed ${feed.capacityKW} kW.`
      );
    }

    feed.loadKW += powerKW;
  }

  allocate(server) {
    if (server.powerPaths.has("A") && server.powerPaths.has("B")) {
      // A genuinely dual-corded server can be treated as resilient to the
      // loss of one path, provided each path has enough independent capacity.
      this.reserve("A", server.powerKW / 2);
      this.reserve("B", server.powerKW / 2);
      return;
    }

    const onlyPath = [...server.powerPaths][0];

    if (!onlyPath) {
      throw new InfrastructureValidationError(
        `${server.name} has no power path.`
      );
    }

    this.reserve(onlyPath, server.powerKW);
  }

  simulateFeedFailure(path, servers) {
    const affected = servers.filter(
      server =>
        server.state === "RUNNING" &&
        server.powerPaths.size === 1 &&
        server.powerPaths.has(path)
    );

    return {
      path,
      survived: affected.length === 0,
      affectedServers: affected.map(server => server.name)
    };
  }
}

class CoolingSystem {
  constructor(name, capacityKW) {
    this.name = name;
    this.capacityKW = capacityKW;
    this.loadKW = 0;
    this.available = true;
  }

  reserve(heatKW) {
    if (!this.available) {
      throw new CapacityError(`${this.name} is unavailable.`);
    }

    if (this.loadKW + heatKW > this.capacityKW) {
      throw new CapacityError(
        `${this.name} cannot absorb another ${heatKW.toFixed(2)} kW.`
      );
    }

    this.loadKW += heatKW;
  }
}

class NetworkFabric {
  constructor(portCapacity) {
    this.switches = {
      "TOR-A": { ports: portCapacity, used: 0, available: true },
      "TOR-B": { ports: portCapacity, used: 0, available: true }
    };
  }

  connectServer(server) {
    const primary = this.switches["TOR-A"];
    const secondary = this.switches["TOR-B"];

    if (!primary.available || primary.used >= primary.ports) {
      throw new CapacityError("Primary top-of-rack switch cannot accept a port.");
    }

    primary.used += 1;

    if (server.networkPorts >= 2) {
      if (!secondary.available || secondary.used >= secondary.ports) {
        throw new CapacityError(
          "Secondary top-of-rack switch cannot accept the redundant port."
        );
      }

      secondary.used += 1;
    }
  }

  simulateSwitchFailure(switchName, servers) {
    const switchData = this.switches[switchName];

    if (!switchData) {
      throw new InfrastructureValidationError(
        `Unknown switch ${switchName}.`
      );
    }

    const affected = servers.filter(server => server.networkPorts < 2);

    return {
      switchName,
      survived: affected.length === 0,
      affectedServers: affected.map(server => server.name)
    };
  }
}

class DataCenter {
  constructor() {
    this.racks = new Map([
      ["R01", new Rack("R01", 42, 8)],
      ["R02", new Rack("R02", 42, 8)]
    ]);

    this.power = new PowerSystem(10);

    // Cooling is deliberately modeled as two systems. Normal capacity and
    // failure capacity are separate engineering questions.
    this.cooling = new Map([
      ["CRAC-A", new CoolingSystem("CRAC-A", 12)],
      ["CRAC-B", new CoolingSystem("CRAC-B", 12)]
    ]);

    this.network = new NetworkFabric(48);
    this.servers = [];
  }

  installServer(server) {
    const rack = this.racks.get(server.rackId);

    if (!rack) {
      throw new InfrastructureValidationError(
        `Rack ${server.rackId} does not exist.`
      );
    }

    // Allocate resources only after all required systems can accommodate the
    // server. This avoids partially registering a server when a later
    // resource allocation fails.
    const projectedCooling = server.powerKW;
    const coolingA = this.cooling.get("CRAC-A");

    if (
      coolingA.loadKW + projectedCooling >
      coolingA.capacityKW
    ) {
      throw new CapacityError(
        `CRAC-A lacks capacity for ${server.name}.`
      );
    }

    if (!rack.canInstall(server)) {
      throw new CapacityError(
        `Rack ${rack.id} lacks rack-space or electrical capacity.`
      );
    }

    this.power.allocate(server);
    coolingA.reserve(projectedCooling);
    this.network.connectServer(server);
    rack.install(server);
    this.servers.push(server);
  }

  get totalITLoadKW() {
    return this.servers
      .filter(server => server.state === "RUNNING")
      .reduce((sum, server) => sum + server.powerKW, 0);
  }

  get totalHeatKW() {
    // Server electrical consumption is used as the thermal load estimate.
    return this.totalITLoadKW;
  }

  calculatePUE(facilityOverheadKW) {
    if (this.totalITLoadKW === 0) {
      throw new Error("PUE requires a positive IT load.");
    }

    return (
      (this.totalITLoadKW + facilityOverheadKW) /
      this.totalITLoadKW
    );
  }

  simulateCoolingFailure(systemName) {
    const failed = this.cooling.get(systemName);

    if (!failed) {
      throw new InfrastructureValidationError(
        `Unknown cooling system ${systemName}.`
      );
    }

    const remainingCapacity = [...this.cooling.values()]
      .filter(system => system.name !== systemName && system.available)
      .reduce((sum, system) => sum + system.capacityKW, 0);

    return {
      systemName,
      survived: remainingCapacity >= this.totalHeatKW,
      requiredKW: this.totalHeatKW,
      remainingCapacityKW: remainingCapacity
    };
  }

  printReport() {
    console.log("\n=== DATA CENTER INFRASTRUCTURE ===");

    for (const rack of this.racks.values()) {
      console.log(
        `${rack.id}: ${rack.usedU}/${rack.capacityU} U, ` +
        `${rack.usedPowerKW.toFixed(2)}/${rack.powerCapacityKW.toFixed(2)} kW`
      );
    }

    console.log(`IT load: ${this.totalITLoadKW.toFixed(2)} kW`);
    console.log(`Thermal load: ${this.totalHeatKW.toFixed(2)} kW`);

    for (const [name, feed] of Object.entries(this.power.feeds)) {
      console.log(
        `Power ${name}: ${feed.loadKW.toFixed(2)}/` +
        `${feed.capacityKW.toFixed(2)} kW`
      );
    }

    for (const [name, system] of this.cooling) {
      console.log(
        `Cooling ${name}: ${system.loadKW.toFixed(2)}/` +
        `${system.capacityKW.toFixed(2)} kW`
      );
    }

    for (const [name, switchData] of Object.entries(this.network.switches)) {
      console.log(
        `${name}: ${switchData.used}/${switchData.ports} ports`
      );
    }
  }
}

function runScenario() {
  const dataCenter = new DataCenter();

  const inventory = [
    {
      name: "DB-PRIMARY",
      rackId: "R01",
      powerKW: 2.4,
      role: "DATABASE",
      networkPorts: 2,
      powerPaths: ["A", "B"]
    },
    {
      name: "APP-01",
      rackId: "R01",
      powerKW: 1.4,
      role: "APPLICATION",
      networkPorts: 2,
      powerPaths: ["A", "B"]
    },
    {
      name: "APP-02",
      rackId: "R02",
      powerKW: 1.4,
      role: "APPLICATION",
      networkPorts: 2,
      powerPaths: ["A", "B"]
    },
    {
      name: "BACKUP-01",
      rackId: "R02",
      powerKW: 1.8,
      role: "BACKUP",
      networkPorts: 2,
      powerPaths: ["A", "B"]
    }
  ];

  for (const definition of inventory) {
    dataCenter.installServer(new Server(definition));
  }

  dataCenter.printReport();

  console.log(
    `Estimated PUE: ${dataCenter.calculatePUE(4).toFixed(3)}`
  );

  console.log("\n=== POWER FAILURE TEST ===");
  console.log(dataCenter.power.simulateFeedFailure("A", dataCenter.servers));

  console.log("\n=== NETWORK FAILURE TEST ===");
  console.log(
    dataCenter.network.simulateSwitchFailure(
      "TOR-A",
      dataCenter.servers
    )
  );

  console.log("\n=== COOLING FAILURE TEST ===");
  console.log(dataCenter.simulateCoolingFailure("CRAC-A"));

  console.log("\n=== EDGE CASE ===");

  try {
    dataCenter.installServer(
      new Server({
        name: "INVALID-SERVER",
        rackId: "R99",
        powerKW: 1,
        role: "TEST"
      })
    );
  } catch (error) {
    console.log(`${error.name}: ${error.message}`);
  }
}

runScenario();
