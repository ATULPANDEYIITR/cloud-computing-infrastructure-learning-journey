#!/usr/bin/env node

"use strict";

const fs = require("node:fs/promises");
const EventEmitter = require("node:events");

class ConstraintError extends Error {}
class TransactionError extends Error {}

const TransactionState = Object.freeze({
    ACTIVE: "ACTIVE",
    COMMITTED: "COMMITTED",
    ROLLED_BACK: "ROLLED_BACK"
});

class RelationalStore extends EventEmitter {
    constructor() {
        super();
        this.users = new Map();
        this.accounts = new Map();
        this.audit = [];
        this.nextUserId = 1;
        this.nextAccountId = 1;
    }

    addUser(username) {
        const normalized = String(username).trim();

        if (!normalized) {
            throw new ConstraintError("Username cannot be empty.");
        }

        for (const user of this.users.values()) {
            if (user.username.toLowerCase() === normalized.toLowerCase()) {
                throw new ConstraintError("Username must be unique.");
            }
        }

        const user = {
            userId: this.nextUserId++,
            username: normalized
        };

        this.users.set(user.userId, user);
        this.emit("userCreated", user);
        return user;
    }

    addAccount(ownerId, balanceCents = 0) {
        if (!this.users.has(ownerId)) {
            throw new ConstraintError("Foreign-key violation: owner does not exist.");
        }

        if (!Number.isSafeInteger(balanceCents) || balanceCents < 0) {
            throw new ConstraintError("Balance must be a non-negative integer.");
        }

        const account = {
            accountId: this.nextAccountId++,
            ownerId,
            balanceCents,
            version: 0
        };

        this.accounts.set(account.accountId, account);
        this.emit("accountCreated", account);
        return account;
    }

    snapshot() {
        return new Map(
            [...this.accounts.entries()].map(([id, account]) => [
                id,
                { ...account }
            ])
        );
    }

    auditEvent(event, details) {
        const entry = {
            event,
            details,
            timestamp: new Date().toISOString()
        };

        this.audit.push(entry);
        this.emit("audit", entry);
    }
}

class Transaction {
    constructor(store) {
        this.store = store;
        this.state = TransactionState.ACTIVE;
        this.staged = store.snapshot();

        this.originalVersions = new Map(
            [...this.staged.entries()].map(([id, account]) => [id, account.version])
        );
    }

    requireActive() {
        if (this.state !== TransactionState.ACTIVE) {
            throw new TransactionError("Transaction is not active.");
        }
    }

    transfer(sourceId, destinationId, amountCents) {
        this.requireActive();

        if (sourceId === destinationId) {
            throw new ConstraintError("Source and destination must differ.");
        }

        if (!Number.isSafeInteger(amountCents) || amountCents <= 0) {
            throw new ConstraintError("Transfer amount must be a positive integer.");
        }

        const source = this.staged.get(sourceId);
        const destination = this.staged.get(destinationId);

        if (!source || !destination) {
            throw new ConstraintError("Both accounts must exist.");
        }

        if (source.balanceCents < amountCents) {
            throw new ConstraintError("Insufficient funds.");
        }

        source.balanceCents -= amountCents;
        destination.balanceCents += amountCents;
    }

    commit() {
        this.requireActive();

        for (const [id, originalVersion] of this.originalVersions) {
            const current = this.store.accounts.get(id);

            if (!current || current.version !== originalVersion) {
                throw new TransactionError(
                    `Concurrent update detected for account ${id}.`
                );
            }
        }

        for (const [id, staged] of this.staged) {
            const current = this.store.accounts.get(id);

            if (
                current.balanceCents !== staged.balanceCents
            ) {
                current.balanceCents = staged.balanceCents;
                current.version += 1;
            }
        }

        this.state = TransactionState.COMMITTED;
        this.store.auditEvent(
            "transaction_commit",
            "Staged account changes committed atomically."
        );
    }

    rollback() {
        this.requireActive();
        this.state = TransactionState.ROLLED_BACK;

        this.store.auditEvent(
            "transaction_rollback",
            "Staged changes discarded."
        );
    }
}

async function runWorkflow() {
    const store = new RelationalStore();

    store.on("audit", entry => {
        console.log(
            `[AUDIT] ${entry.timestamp} ${entry.event}: ${entry.details}`
        );
    });

    store.on("userCreated", user => {
        console.log(`[EVENT] userCreated -> ${user.username}`);
    });

    const alice = store.addUser("alice");
    const bob = store.addUser("bob");

    store.addAccount(alice.userId, 10000);
    store.addAccount(bob.userId, 2500);

    console.log("\nInitial state:");
    console.table([...store.accounts.values()]);

    console.log("\nSuccessful transaction:");
    const successful = new Transaction(store);
    successful.transfer(1, 2, 3000);
    successful.commit();
    console.table([...store.accounts.values()]);

    console.log("\nRollback after validation failure:");
    const failed = new Transaction(store);

    try {
        failed.transfer(1, 2, 100000);
        failed.commit();
    } catch (error) {
        failed.rollback();
        console.log(`Rejected: ${error.message}`);
    }

    console.log("\nConstraint validation:");

    try {
        store.addUser("ALICE");
    } catch (error) {
        console.log(`Duplicate user rejected: ${error.message}`);
    }

    try {
        store.addAccount(999, 100);
    } catch (error) {
        console.log(`Foreign key rejected: ${error.message}`);
    }

    const invariantTotal = [...store.accounts.values()]
        .reduce((sum, account) => sum + account.balanceCents, 0);

    if (invariantTotal !== 12500) {
        throw new Error("Balance conservation invariant failed.");
    }

    const auditDocument = store.audit
        .map(entry =>
            `${entry.timestamp} | ${entry.event} | ${entry.details}`
        )
        .join("\n") + "\n";

    await fs.writeFile(
        "database-audit.log",
        auditDocument,
        { encoding: "utf8", flag: "w" }
    );

    console.log("\nAudit file written: database-audit.log");
}

runWorkflow().catch(error => {
    console.error(`Fatal error: ${error.message}`);
    process.exitCode = 1;
});
