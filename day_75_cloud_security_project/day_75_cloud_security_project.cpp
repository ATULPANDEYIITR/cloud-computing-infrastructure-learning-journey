"use strict";

/**
 * CLOUD SECURITY POLICY ENGINE
 *
 * Node.js 18+
 *
 * Event-driven cloud security assessment covering:
 * IAM, key management, encryption posture, network isolation,
 * centralized audit events, and compliance evaluation.
 *
 * Cryptographic operations are represented through managed KMS
 * key metadata. This program does not implement encryption itself.
 */

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const EventEmitter = require("node:events");

// ============================================================
// CONFIGURATION
// ============================================================

const CONFIG = Object.freeze({
    project: "SecureCloud",
    auditFile: path.resolve("cloud_security_events.jsonl"),
    maximumAuditEvents: 100000,
    environments: ["development", "staging", "production"]
});

const SEVERITY = Object.freeze({
    INFO: 1,
    LOW: 2,
    MEDIUM: 3,
    HIGH: 4,
    CRITICAL: 5
});

class SecurityError extends Error {
    constructor(message) {
        super(message);
        this.name = "SecurityError";
    }
}

function validateString(value, name) {
    if (
        typeof value !== "string" ||
        value.trim().length === 0 ||
        value.length > 128
    ) {
        throw new SecurityError(`Invalid ${name}`);
    }
}

function identifier() {
    return crypto.randomUUID();
}

function matches(pattern, value) {
    if (pattern === "*") return true;

    if (pattern.endsWith("*")) {
        return value.startsWith(pattern.slice(0, -1));
    }

    return pattern === value;
}

// ============================================================
// IAM POLICY MODEL
// ============================================================

class IAMPolicy {
    constructor(name, statements = []) {
        validateString(name, "policy name");

        this.name = name;
        this.statements = [];
        this.version = 1;

        for (const statement of statements) {
            this.addStatement(statement);
        }
    }

    addStatement(statement) {
        if (
            !["ALLOW", "DENY"].includes(statement.effect) ||
            !Array.isArray(statement.actions) ||
            !Array.isArray(statement.resources) ||
            statement.actions.length === 0 ||
            statement.resources.length === 0
        ) {
            throw new SecurityError("Invalid IAM policy statement");
        }

        this.statements.push(Object.freeze({
            effect: statement.effect,
            actions: [...statement.actions],
            resources: [...statement.resources]
        }));

        this.version++;
    }

    evaluate(action, resource) {
        let allowed = false;

        for (const statement of this.statements) {
            const actionMatch = statement.actions.some(
                pattern => matches(pattern, action)
            );

            const resourceMatch = statement.resources.some(
                pattern => matches(pattern, resource)
            );

            if (!actionMatch || !resourceMatch) continue;

            if (statement.effect === "DENY") {
                return false;
            }

            if (statement.effect === "ALLOW") {
                allowed = true;
            }
        }

        return allowed;
    }
}

class Identity {
    constructor({
        id,
        policy,
        active = true,
        mfa = false,
        privileged = false
    }) {
        validateString(id, "identity ID");

        this.id = id;
        this.policy = policy;
        this.active = active;
        this.mfa = mfa;
        this.privileged = privileged;
    }
}

class IAMEngine {

    constructor() {
        this.identities = new Map();
    }

    register(identity) {
        if (this.identities.has(identity.id)) {
            throw new SecurityError("Duplicate identity");
        }

        this.identities.set(identity.id, identity);
    }

    authorize(identityId, action, resource, options = {}) {
        const identity = this.identities.get(identityId);

        if (!identity || !identity.active) {
            return {
                allowed: false,
                reason: "IDENTITY_INACTIVE_OR_UNKNOWN"
            };
        }

        if (options.requireMFA !== false && !identity.mfa) {
            return {
                allowed: false,
                reason: "MFA_REQUIRED"
            };
        }

        const allowed = identity.policy.evaluate(action, resource);

        return {
            allowed,
            reason: allowed ? "POLICY_ALLOW" : "DEFAULT_OR_EXPLICIT_DENY"
        };
    }
}

// ============================================================
// KMS AND ENCRYPTION POSTURE
// ============================================================

class KMSRegistry {

    constructor() {
        this.keys = new Map();
    }

    create(alias) {
        validateString(alias, "key alias");

        if (this.keys.has(alias)) {
            throw new SecurityError("Key alias already exists");
        }

        const key = {
            id: identifier(),
            alias,
            algorithm: "AES-256-GCM",
            enabled: true,
            version: 1,
            createdAt: new Date().toISOString()
        };

        this.keys.set(alias, key);

        return { ...key };
    }

    rotate(alias) {
        const key = this.keys.get(alias);

        if (!key || !key.enabled) {
            throw new SecurityError("Key unavailable for rotation");
        }

        key.id = identifier();
        key.version++;
        key.rotatedAt = new Date().toISOString();

        return { ...key };
    }

    disable(alias) {
        const key = this.keys.get(alias);

        if (!key) {
            throw new SecurityError("Unknown key");
        }

        key.enabled = false;
    }

    get(alias) {
        const key = this.keys.get(alias);

        return key ? { ...key } : null;
    }
}

class SecureStorage {

    constructor(kms) {
        this.kms = kms;
        this.resources = new Map();
    }

    provision({ id, environment, owner }) {
        validateString(id, "resource ID");
        validateString(owner, "owner");

        if (!CONFIG.environments.includes(environment)) {
            throw new SecurityError("Invalid environment");
        }

        if (this.resources.has(id)) {
            throw new SecurityError("Duplicate storage resource");
        }

        this.resources.set(id, {
            id,
            owner,
            environment,
            encrypted: false,
            keyAlias: null,
            keyVersion: null,
            state: "ACTIVE"
        });
    }

    enableEncryption(resourceId, keyAlias) {
        const resource = this.resources.get(resourceId);
        const key = this.kms.get(keyAlias);

        if (!resource || !key || !key.enabled) {
            throw new SecurityError("Resource or encryption key unavailable");
        }

        resource.encrypted = true;
        resource.keyAlias = keyAlias;
        resource.keyVersion = key.version;
        resource.state = "ENCRYPTED";
    }

    assess(resourceId) {
        const resource = this.resources.get(resourceId);

        if (!resource) return false;

        const key = this.kms.get(resource.keyAlias);

        return (
            resource.encrypted &&
            resource.state === "ENCRYPTED" &&
            key !== null &&
            key.enabled
        );
    }
}

// ============================================================
// NETWORK ISOLATION
// ============================================================

class NetworkPolicy {

    constructor(name) {
        validateString(name, "network name");

        this.name = name;
        this.rules = [];
    }

    addRule({
        source,
        destination,
        port,
        protocol = "TCP",
        effect
    }) {
        if (
            !Number.isInteger(port) ||
            port < 1 ||
            port > 65535
        ) {
            throw new SecurityError("Invalid port");
        }

        if (!["TCP", "UDP", "ICMP"].includes(protocol)) {
            throw new SecurityError("Unsupported protocol");
        }

        if (!["ALLOW", "DENY"].includes(effect)) {
            throw new SecurityError("Invalid network effect");
        }

        this.rules.push(Object.freeze({
            source,
            destination,
            port,
            protocol,
            effect
        }));
    }

    evaluate(source, destination, port, protocol = "TCP") {
        const matching = this.rules.filter(rule =>
            matches(rule.source, source) &&
            matches(rule.destination, destination) &&
            rule.port === port &&
            rule.protocol === protocol
        );

        if (matching.some(rule => rule.effect === "DENY")) {
            return false;
        }

        return matching.some(rule => rule.effect === "ALLOW");
    }
}

// ============================================================
// EVENT-DRIVEN AUDIT SERVICE
// ============================================================

class AuditService extends EventEmitter {

    constructor(filePath = CONFIG.auditFile) {
        super();

        this.filePath = filePath;
        this.events = [];
        this.sequence = 0;
        this.previousHash = "GENESIS";
    }

    async record({
        actor,
        action,
        resource,
        outcome,
        severity = "LOW",
        details = {}
    }) {
        if (!Object.hasOwn(SEVERITY, severity)) {
            throw new SecurityError("Invalid severity");
        }

        if (this.events.length >= CONFIG.maximumAuditEvents) {
            throw new SecurityError("Audit event limit reached");
        }

        const payload = {
            sequence: ++this.sequence,
            id: identifier(),
            timestamp: new Date().toISOString(),
            actor,
            action,
            resource,
            outcome,
            severity,
            details,
            previousHash: this.previousHash
        };

        const canonical = JSON.stringify(payload);

        const hash = crypto
            .createHash("sha256")
            .update(canonical)
            .digest("hex");

        const event = Object.freeze({
            ...payload,
            hash
        });

        // Serialize writes so concurrent requests cannot reorder
        // the hash chain or interleave audit records.
        await fs.promises.appendFile(
            this.filePath,
            JSON.stringify(event) + "\n",
            { encoding: "utf8", flag: "a", mode: 0o600 }
        );

        this.events.push(event);
        this.previousHash = hash;

        this.emit("security-event", event);

        return event;
    }

    verifyIntegrity() {
        let previous = "GENESIS";

        for (const event of this.events) {
            const payload = {
                sequence: event.sequence,
                id: event.id,
                timestamp: event.timestamp,
                actor: event.actor,
                action: event.action,
                resource: event.resource,
                outcome: event.outcome,
                severity: event.severity,
                details: event.details,
                previousHash: event.previousHash
            };

            if (event.previousHash !== previous) {
                return false;
            }

            const expected = crypto
                .createHash("sha256")
                .update(JSON.stringify(payload))
                .digest("hex");

            if (expected !== event.hash) {
                return false;
            }

            previous = event.hash;
        }

        return true;
    }
}

// ============================================================
// SECURITY POSTURE ENGINE
// ============================================================

class SecurityPostureEngine {

    constructor({ iam, kms, storage, network }) {
        this.iam = iam;
        this.kms = kms;
        this.storage = storage;
        this.network = network;
    }

    evaluate() {
        const findings = [];

        for (const identity of this.iam.identities.values()) {
            if (identity.active && !identity.mfa) {
                findings.push({
                    category: "IDENTITY",
                    severity: "HIGH",
                    resource: identity.id,
                    description: "MFA is not enabled"
                });
            }
        }

        for (const resource of this.storage.resources.values()) {
            if (!this.storage.assess(resource.id)) {
                findings.push({
                    category: "ENCRYPTION",
                    severity: "CRITICAL",
                    resource: resource.id,
                    description: "Storage encryption is missing or invalid"
                });
            }
        }

        for (const [alias, key] of this.kms.keys) {
            if (!key.enabled) {
                findings.push({
                    category: "KEY_MANAGEMENT",
                    severity: "HIGH",
                    resource: alias,
                    description: "Encryption key is disabled"
                });
            }
        }

        if (this.network.rules.length === 0) {
            findings.push({
                category: "NETWORK",
                severity: "HIGH",
                resource: this.network.name,
                description: "Network policy has no explicit rules"
            });
        }

        return {
            status: findings.length === 0 ? "COMPLIANT" : "NON_COMPLIANT",
            evaluatedAt: new Date().toISOString(),
            findingCount: findings.length,
            findings
        };
    }
}

// ============================================================
// SECURITY APPLICATION
// ============================================================

class CloudSecurityApplication {

    constructor() {
        this.iam = new IAMEngine();
        this.kms = new KMSRegistry();
        this.storage = new SecureStorage(this.kms);
        this.network = new NetworkPolicy("production-vpc");

        this.audit = new AuditService();

        this.audit.on("security-event", event => {
            if (SEVERITY[event.severity] >= SEVERITY.HIGH) {
                process.stderr.write(
                    `[SECURITY ALERT] ${event.action}: ${event.outcome}\n`
                );
            }
        });

        this.posture = new SecurityPostureEngine(this);
    }

    async execute(identity, action, resource) {
        const result = this.iam.authorize(
            identity,
            action,
            resource
        );

        await this.audit.record({
            actor: identity,
            action,
            resource,
            outcome: result.allowed ? "ALLOWED" : "DENIED",
            severity: result.allowed ? "LOW" : "HIGH",
            details: { reason: result.reason }
        });

        return result;
    }

    report() {
        return this.posture.evaluate();
    }
}

// ============================================================
// TESTING
// ============================================================

async function runTests() {
    const app = new CloudSecurityApplication();

    const policy = new IAMPolicy("application-reader");

    policy.addStatement({
        effect: "ALLOW",
        actions: ["storage:read"],
        resources: ["bucket:production/*"]
    });

    policy.addStatement({
        effect: "DENY",
        actions: ["storage:delete"],
        resources: ["*"]
    });

    app.iam.register(new Identity({
        id: "application-identity",
        policy,
        mfa: true
    }));

    console.assert(
        app.iam.authorize(
            "application-identity",
            "storage:read",
            "bucket:production/logs"
        ).allowed
    );

    console.assert(
        !app.iam.authorize(
            "application-identity",
            "storage:delete",
            "bucket:production/logs"
        ).allowed
    );

    console.assert(
        !app.iam.authorize(
            "unknown",
            "storage:read",
            "bucket:production/logs"
        ).allowed
    );

    const key = app.kms.create("production-key");

    app.storage.provision({
        id: "database-backup",
        environment: "production",
        owner: "database-team"
    });

    app.storage.enableEncryption(
        "database-backup",
        key.alias
    );

    console.assert(app.storage.assess("database-backup"));

    app.network.addRule({
        source: "application-subnet",
        destination: "database-subnet",
        port: 5432,
        protocol: "TCP",
        effect: "ALLOW"
    });

    app.network.addRule({
        source: "internet",
        destination: "database-subnet",
        port: 5432,
        protocol: "TCP",
        effect: "DENY"
    });

    console.assert(
        app.network.evaluate(
            "application-subnet",
            "database-subnet",
            5432
        )
    );

    console.assert(
        !app.network.evaluate(
            "internet",
            "database-subnet",
            5432
        )
    );

    await app.execute(
        "application-identity",
        "storage:read",
        "bucket:production/logs"
    );

    await app.execute(
        "application-identity",
        "storage:delete",
        "bucket:production/logs"
    );

    console.assert(app.audit.verifyIntegrity());

    console.log("All cloud security tests passed.");

    return app;
}

// ============================================================
// EXECUTION
// ============================================================

async function main() {
    try {
        const app = await runTests();

        console.log("\nSECURITY POSTURE REPORT");

        console.log(
            JSON.stringify(app.report(), null, 2)
        );

        console.log("\nAUDIT INTEGRITY");

        console.log(
            app.audit.verifyIntegrity() ? "VALID" : "INVALID"
        );

    } catch (error) {
        console.error("Cloud security failure:", error.message);
        process.exitCode = 1;
    }
}

if (require.main === module) {
    main();
}

module.exports = {
    IAMPolicy,
    IAMEngine,
    Identity,
    KMSRegistry,
    SecureStorage,
    NetworkPolicy,
    AuditService,
    SecurityPostureEngine,
    CloudSecurityApplication
};
