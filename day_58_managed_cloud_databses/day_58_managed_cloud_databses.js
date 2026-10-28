#!/usr/bin/env node
"use strict";

/*
 * Managed Cloud Database Operations Simulator
 *
 * Models:
 * - managed database instances
 * - automated backups
 * - patch maintenance
 * - read-replica scaling
 * - health events
 * - failover
 * - policy evaluation
 * - audit events
 *
 * Uses only Node.js standard-library features.
 */

const crypto = require("node:crypto");
const { EventEmitter } = require("node:events");

const DatabaseState = Object.freeze({
  AVAILABLE: "available",
  MAINTENANCE: "maintenance",
  DEGRADED: "degraded",
  FAILED: "failed",
  RESTORING: "restoring",
});

const NodeRole = Object.freeze({
  PRIMARY: "primary",
  REPLICA: "read-replica",
});

const ReviewEvent = Object.freeze({
  BACKUP_CREATED: "backup.created",
  PATCH_STARTED: "patch.started",
  PATCH_COMPLETED: "patch.completed",
  PATCH_FAILED: "patch.failed",
  FAILOVER: "database.failover",
  SCALE: "database.scale",
});

class ValidationError extends Error {}
class OperationalError extends Error {}

function requireCondition(condition, message) {
  if (!condition) throw new ValidationError(message);
}

function utcNow() {
  return new Date();
}

function checksum(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

class AuditLog {
  constructor() {
    this.entries = [];
  }

  add(action, actor, result, details) {
    this.entries.push({
      timestamp: utcNow().toISOString(),
      action,
      actor,
      result,
      details,
    });
  }
}

class DatabaseNode {
  constructor({ id, zone, role, version }) {
    this.id = id;
    this.zone = zone;
    this.role = role;
    this.version = version;
    this.state = DatabaseState.AVAILABLE;
    this.metrics = {
      cpuPercent: 0,
      storagePercent: 0,
      replicationLagSeconds: 0,
      connections: 0,
    };
  }

  isHealthy() {
    return (
      this.state === DatabaseState.AVAILABLE &&
      this.metrics.cpuPercent < 85 &&
      this.metrics.storagePercent < 90 &&
      this.metrics.replicationLagSeconds < 30
    );
  }
}

class ManagedDatabase extends EventEmitter {
  constructor(config) {
    super();

    requireCondition(config.id, "Database id is required.");
    requireCondition(config.name, "Database name is required.");
    requireCondition(config.storageGB >= 10, "Minimum storage is 10 GB.");
    requireCondition(
      Number.isInteger(config.backupRetentionDays) &&
        config.backupRetentionDays >= 1 &&
        config.backupRetentionDays <= 35,
      "Backup retention must be between 1 and 35 days."
    );

    this.id = config.id;
    this.name = config.name;
    this.engine = config.engine;
    this.version = config.version;
    this.region = config.region;
    this.storageGB = config.storageGB;
    this.backupRetentionDays = config.backupRetentionDays;

    this.nodes = new Map();
    this.backups = new Map();
    this.maintenanceEvents = new Map();
    this.audit = new AuditLog();
    this.state = DatabaseState.AVAILABLE;
  }

  log(action, actor, result, details) {
    this.audit.add(action, actor, result, details);
  }

  emitOperationalEvent(event, payload) {
    this.emit(event, payload);
  }

  primary() {
    const nodes = [...this.nodes.values()].filter(
      (node) => node.role === NodeRole.PRIMARY
    );

    requireCondition(nodes.length === 1, "Exactly one primary is required.");
    return nodes[0];
  }

  replicas() {
    return [...this.nodes.values()].filter(
      (node) => node.role === NodeRole.REPLICA
    );
  }

  addNode(zone, role) {
    if (role === NodeRole.PRIMARY) {
      requireCondition(
        ![...this.nodes.values()].some(
          (node) => node.role === NodeRole.PRIMARY
        ),
        "A primary already exists."
      );
    }

    const id = `${this.id}-${crypto.randomBytes(4).toString("hex")}`;
    const node = new DatabaseNode({
      id,
      zone,
      role,
      version: this.version,
    });

    this.nodes.set(id, node);
    return node;
  }

  scaleReplicas(desired, zones) {
    requireCondition(
      Number.isInteger(desired) && desired >= 0 && desired <= 10,
      "Replica count must be between 0 and 10."
    );

    requireCondition(
      desired === 0 || zones.length > 0,
      "Scaling requires availability zones."
    );

    const current = this.replicas();

    if (desired > current.length) {
      for (let i = current.length; i < desired; i++) {
        this.addNode(zones[i % zones.length], NodeRole.REPLICA);
      }
    } else if (desired < current.length) {
      for (let i = desired; i < current.length; i++) {
        this.nodes.delete(current[i].id);
      }
    }

    this.log(
      "scale-replicas",
      "operator",
      "SUCCESS",
      `${current.length} -> ${desired}`
    );

    this.emitOperationalEvent(ReviewEvent.SCALE, {
      databaseId: this.id,
      desired,
    });
  }

  collectMetrics(random = Math.random) {
    for (const node of this.nodes.values()) {
      node.metrics = {
        cpuPercent: random() * 80 + 10,
        storagePercent: random() * 55 + 20,
        replicationLagSeconds:
          node.role === NodeRole.PRIMARY ? 0 : random() * 15,
        connections: Math.floor(random() * 150) + 20,
      };

      node.state = node.isHealthy()
        ? DatabaseState.AVAILABLE
        : DatabaseState.DEGRADED;
    }
  }

  createBackup(type = "snapshot", now = utcNow()) {
    const primary = this.primary();

    if (primary.state !== DatabaseState.AVAILABLE) {
      throw new OperationalError("Primary is unavailable.");
    }

    const id = `bkp-${crypto.randomBytes(6).toString("hex")}`;
    const created = now.toISOString();
    const data = `${this.id}:${this.version}:${created}`;

    const backup = {
      id,
      databaseId: this.id,
      type,
      createdAt: created,
      sizeGB: Math.max(1, this.storageGB * 0.2),
      checksum: checksum(data),
      expiresAt: new Date(
        now.getTime() + this.backupRetentionDays * 86400000
      ).toISOString(),
    };

    this.backups.set(id, backup);
    this.log("backup", "backup-service", "SUCCESS", id);

    this.emitOperationalEvent(ReviewEvent.BACKUP_CREATED, backup);
    return backup;
  }

  purgeExpiredBackups(now = utcNow()) {
    let removed = 0;

    for (const [id, backup] of this.backups) {
      if (new Date(backup.expiresAt) <= now) {
        this.backups.delete(id);
        removed++;
      }
    }

    this.log(
      "purge-backups",
      "backup-service",
      "SUCCESS",
      `Removed ${removed} backups.`
    );

    return removed;
  }

  schedulePatch(targetVersion, scheduledAt) {
    requireCondition(targetVersion !== this.version, "Version is unchanged.");
    requireCondition(
      scheduledAt instanceof Date && !Number.isNaN(scheduledAt.getTime()),
      "Invalid maintenance date."
    );

    const id = `mnt-${crypto.randomBytes(5).toString("hex")}`;

    const event = {
      id,
      scheduledAt: scheduledAt.toISOString(),
      from: this.version,
      to: targetVersion,
      status: "scheduled",
    };

    this.maintenanceEvents.set(id, event);
    return event;
  }

  async runPatch(eventId) {
    const event = this.maintenanceEvents.get(eventId);

    requireCondition(event, "Maintenance event not found.");
    requireCondition(
      event.status === "scheduled",
      "Maintenance event is not executable."
    );

    event.status = "running";
    this.state = DatabaseState.MAINTENANCE;
    this.emitOperationalEvent(ReviewEvent.PATCH_STARTED, event);

    try {
      const backup = this.createBackup("maintenance-snapshot");

      if (!backup.checksum) {
        throw new OperationalError("Backup verification failed.");
      }

      // Sequentially update nodes to model a controlled rolling maintenance event.
      for (const node of this.nodes.values()) {
        node.state = DatabaseState.MAINTENANCE;
        await new Promise((resolve) => setTimeout(resolve, 5));
        node.version = event.to;
        node.state = DatabaseState.AVAILABLE;
      }

      this.version = event.to;
      event.status = "completed";
      this.state = DatabaseState.AVAILABLE;

      this.log(
        "patch",
        "maintenance-service",
        "SUCCESS",
        `${event.from} -> ${event.to}`
      );

      this.emitOperationalEvent(ReviewEvent.PATCH_COMPLETED, {
        event,
        backupId: backup.id,
      });
    } catch (error) {
      event.status = "failed";
      event.error = error.message;
      this.state = DatabaseState.FAILED;

      this.log("patch", "maintenance-service", "FAILED", error.message);
      this.emitOperationalEvent(ReviewEvent.PATCH_FAILED, event);

      throw error;
    }
  }

  failover() {
    const oldPrimary = this.primary();

    const candidates = this.replicas()
      .filter((node) => node.isHealthy())
      .sort(
        (a, b) =>
          a.metrics.replicationLagSeconds -
          b.metrics.replicationLagSeconds
      );

    if (candidates.length === 0) {
      this.state = DatabaseState.FAILED;
      oldPrimary.state = DatabaseState.FAILED;
      throw new OperationalError("No healthy replica is available.");
    }

    const newPrimary = candidates[0];

    oldPrimary.role = NodeRole.REPLICA;
    oldPrimary.state = DatabaseState.DEGRADED;

    newPrimary.role = NodeRole.PRIMARY;
    newPrimary.state = DatabaseState.AVAILABLE;

    this.state = DatabaseState.AVAILABLE;

    this.log(
      "failover",
      "failover-service",
      "SUCCESS",
      `${oldPrimary.id} -> ${newPrimary.id}`
    );

    this.emitOperationalEvent(ReviewEvent.FAILOVER, {
      oldPrimary: oldPrimary.id,
      newPrimary: newPrimary.id,
    });

    return newPrimary;
  }

  evaluatePolicy() {
    const zones = new Set(
      [...this.nodes.values()].map((node) => node.zone)
    );

    const healthyReplicas = this.replicas().filter((node) =>
      node.isHealthy()
    ).length;

    const checks = {
      singlePrimary:
        [...this.nodes.values()].filter(
          (node) => node.role === NodeRole.PRIMARY
        ).length === 1,
      backupRetention: this.backupRetentionDays >= 7,
      multiZone: zones.size >= 2,
      healthyReplica: healthyReplicas >= 1,
      versionConsistency: [...this.nodes.values()].every(
        (node) => node.version === this.version
      ),
    };

    return {
      eligible: Object.values(checks).every(Boolean),
      checks,
    };
  }

  restore(backupId) {
    const backup = this.backups.get(backupId);

    requireCondition(backup, "Backup does not exist.");
    requireCondition(
      new Date(backup.expiresAt) > utcNow(),
      "Backup has expired."
    );

    this.state = DatabaseState.RESTORING;

    const data = `${this.id}:${this.version}:${backup.createdAt}`;
    requireCondition(
      checksum(data) === backup.checksum,
      "Backup checksum mismatch."
    );

    this.state = DatabaseState.AVAILABLE;

    this.log(
      "restore",
      "restore-service",
      "SUCCESS",
      `Restored from ${backupId}`
    );
  }
}

async function main() {
  const database = new ManagedDatabase({
    id: "orders-prod",
    name: "orders",
    engine: "PostgreSQL",
    version: "16.4",
    region: "ap-south-1",
    storageGB: 250,
    backupRetentionDays: 14,
  });

  database.on(ReviewEvent.FAILOVER, (event) => {
    console.log(
      `Failover event: ${event.oldPrimary} -> ${event.newPrimary}`
    );
  });

  database.on(ReviewEvent.PATCH_COMPLETED, (event) => {
    console.log(`Patch completed: ${event.event.to}`);
  });

  database.addNode("zone-a", NodeRole.PRIMARY);
  database.addNode("zone-b", NodeRole.REPLICA);
  database.scaleReplicas(2, ["zone-b", "zone-c"]);

  database.collectMetrics(() => 0.4);

  const backup = database.createBackup("full");

  const maintenance = database.schedulePatch(
    "16.5",
    new Date(Date.now() + 60000)
  );

  await database.runPatch(maintenance.id);

  database.collectMetrics(() => 0.25);

  const policy = database.evaluatePolicy();

  if (!policy.eligible) {
    console.log("Policy warnings:", policy.checks);
  }

  database.restore(backup.id);

  console.log({
    database: database.name,
    version: database.version,
    state: database.state,
    nodes: database.nodes.size,
    backups: database.backups.size,
    policyEligible: policy.eligible,
    auditEvents: database.audit.entries.length,
  });

  if (database.primary().role !== NodeRole.PRIMARY) {
    database.failover();
  }
}

main().catch((error) => {
  console.error(`Operation failed: ${error.message}`);
  process.exitCode = 1;
});
