"use strict";

/*
 * Database High Availability: event-driven failover coordinator.
 *
 * This Node.js implementation uses asynchronous health probes, an external
 * fencing adapter, event notifications, quorum evaluation, and serialized
 * promotion requests. It models control-plane decisions; it does not create
 * actual database replicas or configure network infrastructure.
 */

const { EventEmitter } = require("node:events");

const Role = Object.freeze({
  PRIMARY: "primary",
  REPLICA: "replica",
});

const Health = Object.freeze({
  HEALTHY: "healthy",
  DEGRADED: "degraded",
  UNREACHABLE: "unreachable",
  UNKNOWN: "unknown",
});

const ReplicationMode = Object.freeze({
  SYNCHRONOUS: "synchronous",
  ASYNCHRONOUS: "asynchronous",
});

class ValidationError extends Error {
  constructor(message) {
    super(message);
    this.name = "ValidationError";
  }
}

class FailoverError extends Error {
  constructor(message, reasons = []) {
    super(message);
    this.name = "FailoverError";
    this.reasons = reasons;
  }
}

function requireNonEmpty(value, field) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new ValidationError(`${field} must be a non-empty string`);
  }
}

function requireNonNegativeInteger(value, field) {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new ValidationError(`${field} must be a non-negative integer`);
  }
}

class DatabaseNode {
  constructor({
    id,
    zone,
    role,
    votingMember,
    replicationMode,
    replicationLagMs,
    health = Health.UNKNOWN,
    observedAt = new Date(0),
    fenced = false,
    fencingToken = 0,
  }) {
    requireNonEmpty(id, "Node ID");
    requireNonEmpty(zone, "Availability zone");
    requireNonNegativeInteger(replicationLagMs, "Replication lag");
    requireNonNegativeInteger(fencingToken, "Fencing token");

    if (!Object.values(Role).includes(role)) {
      throw new ValidationError(`Invalid role: ${role}`);
    }
    if (!Object.values(ReplicationMode).includes(replicationMode)) {
      throw new ValidationError(`Invalid replication mode: ${replicationMode}`);
    }
    if (typeof votingMember !== "boolean" || typeof fenced !== "boolean") {
      throw new ValidationError("Voting and fencing flags must be boolean");
    }
    if (!Object.values(Health).includes(health)) {
      throw new ValidationError(`Invalid health status: ${health}`);
    }
    if (!(observedAt instanceof Date) || Number.isNaN(observedAt.getTime())) {
      throw new ValidationError("Health observation must be a valid Date");
    }

    this.id = id;
    this.zone = zone;
    this.role = role;
    this.votingMember = votingMember;
    this.replicationMode = replicationMode;
    this.replicationLagMs = replicationLagMs;
    this.health = health;
    this.observedAt = new Date(observedAt);
    this.fenced = fenced;
    this.fencingToken = fencingToken;
  }

  applyObservation(observation) {
    if (!Object.values(Health).includes(observation.health)) {
      throw new ValidationError("Probe returned an invalid health status");
    }

    requireNonNegativeInteger(
      observation.replicationLagMs,
      "Observed replication lag",
    );

    const observedAt = new Date(observation.observedAt ?? Date.now());
    if (Number.isNaN(observedAt.getTime())) {
      throw new ValidationError("Probe returned an invalid timestamp");
    }

    this.health = observation.health;
    this.replicationLagMs = observation.replicationLagMs;
    this.observedAt = observedAt;
  }
}

class DatabaseCluster {
  constructor({ id, nodes, primaryNodeId, policy, epoch = 1, fencingToken = 1 }) {
    requireNonEmpty(id, "Cluster ID");
    requireNonEmpty(primaryNodeId, "Primary node ID");
    requireNonNegativeInteger(epoch, "Cluster epoch");
    requireNonNegativeInteger(fencingToken, "Cluster fencing token");

    if (!Array.isArray(nodes) || nodes.length < 2) {
      throw new ValidationError("A cluster requires at least two nodes");
    }

    this.nodes = new Map();
    for (const node of nodes) {
      if (!(node instanceof DatabaseNode)) {
        throw new ValidationError("Every cluster member must be a DatabaseNode");
      }
      if (this.nodes.has(node.id)) {
        throw new ValidationError(`Duplicate node ID: ${node.id}`);
      }
      this.nodes.set(node.id, node);
    }

    if (!this.nodes.has(primaryNodeId)) {
      throw new ValidationError("Current primary is not a cluster member");
    }

    const primaryCount = [...this.nodes.values()].filter(
      (node) => node.role === Role.PRIMARY,
    ).length;

    if (primaryCount !== 1 || this.nodes.get(primaryNodeId).role !== Role.PRIMARY) {
      throw new ValidationError("Cluster must have exactly one identified primary");
    }

    const voters = [...this.nodes.values()].filter(
      (node) => node.votingMember,
    ).length;
    const zones = new Set([...this.nodes.values()].map((node) => node.zone));

    if (policy.quorumRequired < 1 || policy.quorumRequired > voters) {
      throw new ValidationError("Quorum requirement exceeds voting membership");
    }
    if (zones.size < policy.minimumAvailabilityZones) {
      throw new ValidationError("Cluster does not meet its zone requirement");
    }
    if (policy.maximumObservationAgeMs <= 0) {
      throw new ValidationError("Observation freshness limit must be positive");
    }
    requireNonNegativeInteger(
      policy.maxReplicationLagMs,
      "Maximum replication lag",
    );

    this.id = id;
    this.primaryNodeId = primaryNodeId;
    this.policy = Object.freeze({ ...policy });
    this.epoch = epoch;
    this.fencingToken = fencingToken;
  }
}

class FailoverCoordinator extends EventEmitter {
  constructor(cluster, fencingAdapter) {
    super();

    if (!(cluster instanceof DatabaseCluster)) {
      throw new ValidationError("A valid DatabaseCluster is required");
    }
    if (typeof fencingAdapter !== "function") {
      throw new ValidationError("A fencing adapter function is required");
    }

    this.cluster = cluster;
    this.fencingAdapter = fencingAdapter;

    // Each operation waits for the previous operation. A rejected operation
    // does not permanently poison the queue.
    this.operationTail = Promise.resolve();
    this.events = [];
  }

  isFresh(node, now) {
    const age = now.getTime() - node.observedAt.getTime();
    return (
      Number.isFinite(age) &&
      age >= 0 &&
      age <= this.cluster.policy.maximumObservationAgeMs
    );
  }

  evaluate(candidateId, now = new Date()) {
    const { nodes, policy, primaryNodeId } = this.cluster;
    const candidate = nodes.get(candidateId);

    if (!candidate) {
      return {
        eligible: false,
        reasons: ["candidate_not_found"],
        healthyVoters: 0,
      };
    }

    const primary = nodes.get(primaryNodeId);
    const reasons = [];

    if (candidateId === primaryNodeId) {
      reasons.push("candidate_is_already_primary");
    }
    if (candidate.role !== Role.REPLICA) {
      reasons.push("candidate_is_not_a_replica");
    }
    if (candidate.health !== Health.HEALTHY) {
      reasons.push("candidate_is_not_healthy");
    }
    if (!this.isFresh(candidate, now)) {
      reasons.push("candidate_health_observation_is_stale");
    }
    if (
      policy.requireSynchronousReplica &&
      candidate.replicationMode !== ReplicationMode.SYNCHRONOUS
    ) {
      reasons.push("candidate_is_not_synchronous");
    }
    if (candidate.replicationLagMs > policy.maxReplicationLagMs) {
      reasons.push("candidate_replication_lag_exceeds_policy");
    }

    if (
      primary.health === Health.HEALTHY &&
      this.isFresh(primary, now)
    ) {
      reasons.push("current_primary_is_still_healthy");
    }
    if (!primary.fenced) {
      reasons.push("current_primary_has_not_been_fenced");
    }

    const healthyVoters = [...nodes.values()].filter(
      (node) =>
        node.votingMember &&
        node.health === Health.HEALTHY &&
        this.isFresh(node, now),
    ).length;

    if (healthyVoters < policy.quorumRequired) {
      reasons.push("healthy_voter_quorum_not_reached");
    }

    return {
      eligible: reasons.length === 0,
      reasons,
      healthyVoters,
      candidateId,
      candidateLagMs: candidate.replicationLagMs,
    };
  }

  async collectHealth(probeFunction) {
    if (typeof probeFunction !== "function") {
      throw new ValidationError("A health probe function is required");
    }

    const now = new Date();
    const entries = [...this.cluster.nodes.values()];

    // allSettled prevents one failed probe from suppressing other node results.
    const results = await Promise.allSettled(
      entries.map(async (node) => {
        const observation = await probeFunction({
          id: node.id,
          zone: node.zone,
        });
        node.applyObservation(observation);
        return { nodeId: node.id, health: node.health };
      }),
    );

    return results.map((result, index) => {
      if (result.status === "fulfilled") {
        return result.value;
      }

      // A failed probe is recorded as unreachable, not silently treated
      // as a healthy node or as proof that a primary has been fenced.
      const node = entries[index];
      node.health = Health.UNREACHABLE;
      node.observedAt = now;

      return {
        nodeId: node.id,
        health: node.health,
        probeError: String(result.reason?.message ?? result.reason),
      };
    });
  }

  serialize(operation) {
    const result = this.operationTail.then(operation);
    this.operationTail = result.catch(() => undefined);
    return result;
  }

  async failover(candidateId, expectedEpoch) {
    return this.serialize(async () => {
      if (expectedEpoch !== this.cluster.epoch) {
        throw new FailoverError(
          `Stale epoch: expected ${expectedEpoch}, current ${this.cluster.epoch}`,
        );
      }

      const oldPrimary = this.cluster.nodes.get(this.cluster.primaryNodeId);
      if (!oldPrimary) {
        throw new FailoverError("Current primary is missing from cluster state");
      }

      // Fencing must be confirmed by an independent infrastructure adapter.
      // A network timeout or an unhealthy probe is not fencing confirmation.
      if (!oldPrimary.fenced) {
        const receipt = await this.fencingAdapter(oldPrimary.id);

        if (
          !receipt ||
          receipt.nodeId !== oldPrimary.id ||
          typeof receipt.proofId !== "string" ||
          receipt.proofId.trim() === ""
        ) {
          throw new FailoverError("Fencing service did not provide valid proof");
        }

        oldPrimary.fenced = true;
        this.emit("primary-fenced", {
          nodeId: oldPrimary.id,
          proofId: receipt.proofId,
        });
      }

      const decision = this.evaluate(candidateId);
      if (!decision.eligible) {
        this.emit("promotion-rejected", decision);
        throw new FailoverError(
          `Promotion rejected: ${decision.reasons.join(", ")}`,
          decision.reasons,
        );
      }

      const newPrimary = this.cluster.nodes.get(candidateId);
      const oldEpoch = this.cluster.epoch;
      const nextEpoch = oldEpoch + 1;
      const nextFencingToken = this.cluster.fencingToken + 1;

      oldPrimary.role = Role.REPLICA;
      newPrimary.role = Role.PRIMARY;
      newPrimary.fenced = false;
      newPrimary.fencingToken = nextFencingToken;

      this.cluster.primaryNodeId = newPrimary.id;
      this.cluster.epoch = nextEpoch;
      this.cluster.fencingToken = nextFencingToken;

      const event = Object.freeze({
        timestamp: new Date().toISOString(),
        clusterId: this.cluster.id,
        oldPrimaryId: oldPrimary.id,
        newPrimaryId: newPrimary.id,
        previousEpoch: oldEpoch,
        newEpoch: nextEpoch,
        fencingToken: nextFencingToken,
        healthyVoters: decision.healthyVoters,
      });

      this.events.push(event);
      this.emit("primary-promoted", event);
      return event;
    });
  }

  getState() {
    return {
      clusterId: this.cluster.id,
      primaryNodeId: this.cluster.primaryNodeId,
      epoch: this.cluster.epoch,
      fencingToken: this.cluster.fencingToken,
      nodes: [...this.cluster.nodes.values()].map((node) => ({
        id: node.id,
        zone: node.zone,
        role: node.role,
        health: node.health,
        replicationMode: node.replicationMode,
        replicationLagMs: node.replicationLagMs,
        fenced: node.fenced,
        fencingToken: node.fencingToken,
      })),
      events: [...this.events],
    };
  }
}

async function main() {
  const nodes = [
    new DatabaseNode({
      id: "db-az1-primary",
      zone: "availability-zone-a",
      role: Role.PRIMARY,
      votingMember: true,
      replicationMode: ReplicationMode.SYNCHRONOUS,
      replicationLagMs: 0,
    }),
    new DatabaseNode({
      id: "db-az2-replica",
      zone: "availability-zone-b",
      role: Role.REPLICA,
      votingMember: true,
      replicationMode: ReplicationMode.SYNCHRONOUS,
      replicationLagMs: 15,
    }),
    new DatabaseNode({
      id: "db-az3-replica",
      zone: "availability-zone-c",
      role: Role.REPLICA,
      votingMember: true,
      replicationMode: ReplicationMode.ASYNCHRONOUS,
      replicationLagMs: 160,
    }),
  ];

  const cluster = new DatabaseCluster({
    id: "orders-production",
    nodes,
    primaryNodeId: "db-az1-primary",
    epoch: 7,
    fencingToken: 14,
    policy: {
      quorumRequired: 2,
      maxReplicationLagMs: 100,
      requireSynchronousReplica: true,
      maximumObservationAgeMs: 30_000,
      minimumAvailabilityZones: 3,
    },
  });

  const fencingAdapter = async (nodeId) => {
    // Replace this adapter with an independently authenticated infrastructure
    // operation, such as revoking the failed primary's write lease.
    return {
      nodeId,
      proofId: `fencing-confirmation-${nodeId}`,
      confirmedAt: new Date().toISOString(),
    };
  };

  const coordinator = new FailoverCoordinator(cluster, fencingAdapter);

  coordinator.on("primary-fenced", (event) => {
    console.log("Fencing confirmed:", event);
  });

  coordinator.on("primary-promoted", (event) => {
    console.log("Primary promoted:", event);
  });

  coordinator.on("promotion-rejected", (decision) => {
    console.log("Promotion rejected:", decision.reasons);
  });

  // The probe adapter represents monitoring data obtained from each zone.
  await coordinator.collectHealth(async ({ id }) => {
    const observations = {
      "db-az1-primary": {
        health: Health.UNREACHABLE,
        replicationLagMs: 0,
      },
      "db-az2-replica": {
        health: Health.HEALTHY,
        replicationLagMs: 15,
      },
      "db-az3-replica": {
        health: Health.HEALTHY,
        replicationLagMs: 160,
      },
    };

    return {
      ...observations[id],
      observedAt: new Date(),
    };
  });

  const rejected = coordinator.evaluate("db-az3-replica");
  console.log("\nAsynchronous replica evaluation:");
  console.log(JSON.stringify(rejected, null, 2));

  try {
    await coordinator.failover("db-az3-replica", 7);
  } catch (error) {
    if (!(error instanceof FailoverError)) {
      throw error;
    }
    console.log("\nExpected failed promotion:", error.message);
  }

  // The failed candidate attempt leaves the former primary fenced.
  // A second candidate can be evaluated without re-enabling the old writer.
  const eligible = coordinator.evaluate("db-az2-replica");
  console.log("\nSynchronous replica evaluation:");
  console.log(JSON.stringify(eligible, null, 2));

  if (!eligible.eligible) {
    throw new FailoverError(
      "Expected replica was not eligible",
      eligible.reasons,
    );
  }

  await coordinator.failover("db-az2-replica", 7);

  console.log("\nFinal cluster state:");
  console.log(JSON.stringify(coordinator.getState(), null, 2));

  try {
    await coordinator.failover("db-az3-replica", 7);
  } catch (error) {
    console.log("\nExpected stale-epoch protection:", error.message);
  }
}

if (require.main === module) {
  main().catch((error) => {
    console.error("Fatal execution error:", error.message);
    process.exitCode = 1;
  });
}

module.exports = {
  DatabaseNode,
  DatabaseCluster,
  FailoverCoordinator,
  FailoverError,
  Health,
  Role,
  ReplicationMode,
};
