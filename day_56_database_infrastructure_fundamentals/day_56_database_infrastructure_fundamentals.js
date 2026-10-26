"use strict";

/*
 * Database infrastructure model:
 * storage engine -> transactions -> WAL -> replication -> failover.
 *
 * This is intentionally event-driven so operational events can be observed
 * without coupling transaction processing to monitoring logic.
 */

const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");

class DatabaseError extends Error {}
class ConstraintViolation extends DatabaseError {}
class TransactionError extends DatabaseError {}
class ReplicationError extends DatabaseError {}

const TransactionState = Object.freeze({
  ACTIVE: "active",
  COMMITTED: "committed",
  ROLLED_BACK: "rolled_back"
});

const NodeRole = Object.freeze({
  PRIMARY: "primary",
  REPLICA: "replica"
});

class StorageEngine {
  constructor() {
    this.pages = new Map();
  }

  read(key) {
    return this.pages.has(key)
      ? structuredClone(this.pages.get(key))
      : undefined;
  }

  write(key, value) {
    if (!key || typeof key !== "string") {
      throw new ConstraintViolation("Storage key must be a non-empty string.");
    }
    this.pages.set(key, structuredClone(value));
  }

  delete(key) {
    this.pages.delete(key);
  }

  snapshot() {
    return new Map(
      [...this.pages.entries()].map(([key, value]) => [
        key,
        structuredClone(value)
      ])
    );
  }

  restore(snapshot) {
    this.pages = new Map(
      [...snapshot.entries()].map(([key, value]) => [
        key,
        structuredClone(value)
      ])
    );
  }
}

class WriteAheadLog {
  constructor() {
    this.records = [];
    this.nextLSN = 1;
  }

  append(transactionId, operation, key, value) {
    const record = Object.freeze({
      lsn: this.nextLSN++,
      transactionId,
      operation,
      key,
      value: structuredClone(value),
      timestamp: new Date().toISOString()
    });

    this.records.push(record);
    return record;
  }
}

class Transaction {
  constructor(id) {
    this.id = id;
    this.state = TransactionState.ACTIVE;
    this.operations = [];
  }

  ensureActive() {
    if (this.state !== TransactionState.ACTIVE) {
      throw new TransactionError(
        `Transaction ${this.id} is ${this.state}.`
      );
    }
  }

  put(key, value) {
    this.ensureActive();
    this.operations.push({ operation: "put", key, value });
  }

  delete(key) {
    this.ensureActive();
    this.operations.push({ operation: "delete", key, value: null });
  }
}

class TransactionManager {
  constructor(engine, wal) {
    this.engine = engine;
    this.wal = wal;
    this.transactions = new Map();
  }

  begin() {
    const id = crypto.randomUUID();
    const tx = new Transaction(id);
    this.transactions.set(id, tx);
    return tx;
  }

  commit(tx) {
    tx.ensureActive();

    const before = this.engine.snapshot();
    const records = [];

    try {
      for (const operation of tx.operations) {
        if (operation.operation === "put") {
          this.engine.write(operation.key, operation.value);
        } else {
          this.engine.delete(operation.key);
        }

        records.push(
          this.wal.append(
            tx.id,
            operation.operation,
            operation.key,
            operation.value
          )
        );
      }

      tx.state = TransactionState.COMMITTED;
      this.emitCommit(tx, records);
      return records;
    } catch (error) {
      this.engine.restore(before);
      throw error;
    }
  }

  rollback(tx) {
    tx.ensureActive();
    tx.operations.length = 0;
    tx.state = TransactionState.ROLLED_BACK;
  }

  emitCommit(tx, records) {
    if (this.onCommit) {
      this.onCommit({ transaction: tx, records });
    }
  }
}

class DatabaseNode extends EventEmitter {
  constructor(name, role) {
    super();
    this.name = name;
    this.role = role;
    this.engine = new StorageEngine();
    this.available = true;
    this.appliedLSN = 0;
  }

  apply(record) {
    if (!this.available) {
      throw new ReplicationError(`${this.name} is unavailable.`);
    }

    if (record.lsn <= this.appliedLSN) {
      return;
    }

    if (record.operation === "put") {
      this.engine.write(record.key, record.value);
    } else if (record.operation === "delete") {
      this.engine.delete(record.key);
    } else {
      throw new ReplicationError(
        `Unsupported WAL operation: ${record.operation}`
      );
    }

    this.appliedLSN = record.lsn;
    this.emit("walApplied", {
      node: this.name,
      lsn: record.lsn
    });
  }
}

class ReplicationCluster extends EventEmitter {
  constructor(primaryName) {
    super();
    this.primary = new DatabaseNode(primaryName, NodeRole.PRIMARY);
    this.replicas = [];
  }

  addReplica(name) {
    const replica = new DatabaseNode(name, NodeRole.REPLICA);
    this.replicas.push(replica);

    replica.on("walApplied", event => {
      this.emit("replication", event);
    });

    return replica;
  }

  async replicate(records) {
    const results = [];

    for (const replica of this.replicas) {
      if (!replica.available) continue;

      // Yield between nodes to model asynchronous replication work.
      await new Promise(resolve => setImmediate(resolve));

      for (const record of records) {
        replica.apply(record);
      }

      results.push({
        node: replica.name,
        lsn: replica.appliedLSN
      });
    }

    return results;
  }

  failover() {
    const candidates = this.replicas
      .filter(node => node.available)
      .sort((a, b) => b.appliedLSN - a.appliedLSN);

    if (candidates.length === 0) {
      throw new ReplicationError("No healthy replica available for failover.");
    }

    const promoted = candidates[0];

    this.primary.role = NodeRole.REPLICA;
    promoted.role = NodeRole.PRIMARY;
    this.primary = promoted;

    this.emit("failover", {
      newPrimary: promoted.name,
      lsn: promoted.appliedLSN
    });

    return promoted;
  }

  health() {
    return {
      primary: {
        name: this.primary.name,
        available: this.primary.available,
        lsn: this.primary.appliedLSN
      },
      replicas: this.replicas
        .filter(node => node !== this.primary)
        .map(node => ({
          name: node.name,
          available: node.available,
          lsn: node.appliedLSN,
          lag: this.primary.appliedLSN - node.appliedLSN
        }))
    };
  }
}

class AccountService {
  constructor(transactionManager) {
    this.tm = transactionManager;
  }

  createAccount(tx, id, owner, balance) {
    if (!id || !owner.trim()) {
      throw new ConstraintViolation("Account ID and owner are required.");
    }
    if (!Number.isFinite(balance) || balance < 0) {
      throw new ConstraintViolation("Balance must be a finite non-negative number.");
    }

    const key = `account:${id}`;

    if (this.tm.engine.read(key)) {
      throw new ConstraintViolation(`Account ${id} already exists.`);
    }

    tx.put(key, {
      accountId: id,
      owner,
      balance: Number(balance.toFixed(2))
    });
  }

  transfer(tx, sourceId, targetId, amount) {
    if (sourceId === targetId) {
      throw new ConstraintViolation("Source and target accounts must differ.");
    }
    if (!Number.isFinite(amount) || amount <= 0) {
      throw new ConstraintViolation("Transfer amount must be positive.");
    }

    const sourceKey = `account:${sourceId}`;
    const targetKey = `account:${targetId}`;

    const source = this.tm.engine.read(sourceKey);
    const target = this.tm.engine.read(targetKey);

    if (!source || !target) {
      throw new ConstraintViolation("Both accounts must exist.");
    }

    if (source.balance < amount) {
      throw new ConstraintViolation("Insufficient funds.");
    }

    source.balance = Number((source.balance - amount).toFixed(2));
    target.balance = Number((target.balance + amount).toFixed(2));

    tx.put(sourceKey, source);
    tx.put(targetKey, target);
  }
}

async function checkpoint(data) {
  const directory = await fs.mkdtemp(
    path.join(os.tmpdir(), "db-infrastructure-")
  );

  const file = path.join(directory, "checkpoint.json");

  await fs.writeFile(
    file,
    JSON.stringify(data, null, 2),
    { encoding: "utf8", mode: 0o600 }
  );

  return file;
}

async function main() {
  const cluster = new ReplicationCluster("db-primary-01");
  const replicaA = cluster.addReplica("db-replica-01");
  const replicaB = cluster.addReplica("db-replica-02");

  const wal = new WriteAheadLog();
  const tm = new TransactionManager(cluster.primary.engine, wal);
  const accounts = new AccountService(tm);

  cluster.on("replication", event => {
    console.log(`WAL replicated to ${event.node}, LSN=${event.lsn}`);
  });

  cluster.on("failover", event => {
    console.log(`Failover completed: ${event.newPrimary}`);
  });

  const createTx = tm.begin();
  accounts.createAccount(createTx, "A100", "Operations", 1000);
  accounts.createAccount(createTx, "A200", "Analytics", 250);
  const createRecords = tm.commit(createTx);
  await cluster.replicate(createRecords);

  const transferTx = tm.begin();
  accounts.transfer(transferTx, "A100", "A200", 125);
  const transferRecords = tm.commit(transferTx);
  await cluster.replicate(transferRecords);

  if (replicaA.engine.read("account:A200").balance !== 375) {
    throw new Error("Replica consistency assertion failed.");
  }

  const failedTx = tm.begin();

  try {
    accounts.transfer(failedTx, "A100", "A200", 5000);
    tm.commit(failedTx);
  } catch (error) {
    tm.rollback(failedTx);

    if (!(error instanceof ConstraintViolation)) {
      throw error;
    }
  }

  replicaB.available = false;

  const healthBeforeFailover = cluster.health();
  const promoted = cluster.failover();

  const checkpointFile = await checkpoint({
    cluster: cluster.health(),
    promotedPrimary: promoted.name,
    walRecords: wal.records.length
  });

  console.log("\nDatabase infrastructure event model");
  console.log("-----------------------------------");
  console.log(JSON.stringify(healthBeforeFailover, null, 2));
  console.log("Promoted primary:", promoted.name);
  console.log("A100:", promoted.engine.read("account:A100"));
  console.log("A200:", promoted.engine.read("account:A200"));
  console.log("Checkpoint:", checkpointFile);
  console.log("WAL records:", wal.records.length);
}

main().catch(error => {
  console.error("Fatal infrastructure error:", error.message);
  process.exitCode = 1;
});
