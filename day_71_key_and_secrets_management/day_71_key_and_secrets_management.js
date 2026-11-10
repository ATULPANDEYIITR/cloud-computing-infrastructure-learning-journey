"use strict";

/*
 * Key and Secrets Management
 * Node.js 20+
 *
 * Demonstrates:
 * - AES-256-GCM authenticated encryption
 * - HMAC-SHA256 integrity
 * - Key versioning and rotation
 * - Envelope encryption
 * - Secret storage
 * - Certificate inventory
 * - Role-based authorization
 * - Asynchronous lifecycle operations
 * - Audit logging
 *
 * Run: node key_management.js
 */

const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const { EventEmitter } = require("node:events");

// ============================================================
// CONSTANTS AND ERRORS
// ============================================================

const KeyStatus = Object.freeze({
    ACTIVE: "ACTIVE",
    DECRYPT_ONLY: "DECRYPT_ONLY",
    REVOKED: "REVOKED",
    DESTROYED: "DESTROYED"
});

const Permissions = Object.freeze({
    READ: "READ",
    WRITE: "WRITE",
    ROTATE: "ROTATE",
    REVOKE: "REVOKE",
    ADMIN: "ADMIN"
});

class SecurityError extends Error {}
class AccessDenied extends SecurityError {}
class InvalidKeyState extends SecurityError {}
class ResourceNotFound extends SecurityError {}

// ============================================================
// AUDIT EVENT SYSTEM
// ============================================================

class AuditBus extends EventEmitter {
    constructor() {
        super();
        this.events = [];
    }

    record(actor, action, resource, outcome = "SUCCESS") {
        const event = Object.freeze({
            id: crypto.randomUUID(),
            timestamp: new Date().toISOString(),
            actor,
            action,
            resource,
            outcome
        });

        this.events.push(event);
        this.emit("audit", event);
    }

    async export(filename) {
        await fs.writeFile(
            filename,
            JSON.stringify(this.events, null, 2),
            { encoding: "utf8", mode: 0o600 }
        );
    }
}

// ============================================================
// ACCESS CONTROL
// ============================================================

class AuthorizationService {
    constructor() {
        this.roles = new Map();
        this.assignments = new Map();

        this.roles.set("security-admin", new Set(
            Object.values(Permissions)
        ));

        this.roles.set("application", new Set([
            Permissions.READ,
            Permissions.WRITE
        ]));

        this.roles.set("auditor", new Set([
            Permissions.READ
        ]));
    }

    assign(principal, role) {
        if (!this.roles.has(role)) {
            throw new SecurityError(`Unknown role: ${role}`);
        }

        this.assignments.set(principal, role);
    }

    authorize(principal, permission) {
        const role = this.assignments.get(principal);
        const granted = this.roles.get(role);

        if (!granted || !granted.has(permission)) {
            throw new AccessDenied(
                `${principal} cannot perform ${permission}`
            );
        }
    }
}

// ============================================================
// KEY PROVIDER
// ============================================================

class LocalKeyProvider {
    generate() {
        return crypto.randomBytes(32);
    }

    fingerprint(material) {
        return crypto
            .createHash("sha256")
            .update(material)
            .digest("hex");
    }

    encrypt(material, plaintext, aad = "") {
        const iv = crypto.randomBytes(12);

        const cipher = crypto.createCipheriv(
            "aes-256-gcm",
            material,
            iv
        );

        cipher.setAAD(Buffer.from(aad));

        const ciphertext = Buffer.concat([
            cipher.update(plaintext),
            cipher.final()
        ]);

        return {
            algorithm: "AES-256-GCM",
            iv: iv.toString("base64"),
            ciphertext: ciphertext.toString("base64"),
            authenticationTag: cipher.getAuthTag().toString("base64")
        };
    }

    decrypt(material, envelope, aad = "") {
        if (envelope.algorithm !== "AES-256-GCM") {
            throw new SecurityError("Unsupported encryption algorithm");
        }

        const decipher = crypto.createDecipheriv(
            "aes-256-gcm",
            material,
            Buffer.from(envelope.iv, "base64")
        );

        decipher.setAAD(Buffer.from(aad));

        decipher.setAuthTag(
            Buffer.from(envelope.authenticationTag, "base64")
        );

        return Buffer.concat([
            decipher.update(
                Buffer.from(envelope.ciphertext, "base64")
            ),
            decipher.final()
        ]);
    }

    createHmac(material, message) {
        return crypto
            .createHmac("sha256", material)
            .update(message)
            .digest("hex");
    }

    verifyHmac(material, message, signature) {
        const expected = Buffer.from(
            this.createHmac(material, message),
            "hex"
        );

        const supplied = Buffer.from(signature, "hex");

        return supplied.length === expected.length &&
            crypto.timingSafeEqual(expected, supplied);
    }
}

// ============================================================
// KEY MANAGEMENT SERVICE
// ============================================================

class KeyManagementService {
    constructor(provider, authorization, audit) {
        this.provider = provider;
        this.authorization = authorization;
        this.audit = audit;

        this.keys = new Map();
        this.aliases = new Map();
    }

    createKey(actor, alias, options = {}) {
        this.authorization.authorize(actor, Permissions.WRITE);

        if (typeof alias !== "string" ||
            !/^[a-zA-Z0-9/_-]{1,100}$/.test(alias)) {
            throw new TypeError("Invalid key alias");
        }

        const validityDays = options.validityDays ?? 365;

        if (!Number.isInteger(validityDays) ||
            validityDays < 1 || validityDays > 3650) {
            throw new RangeError("Invalid validity period");
        }

        const material = this.provider.generate();
        const versions = this.aliases.get(alias) ?? [];

        const key = {
            id: crypto.randomUUID(),
            alias,
            version: versions.length + 1,
            algorithm: "AES-256-GCM",
            status: KeyStatus.ACTIVE,
            createdAt: new Date(),
            expiresAt: new Date(
                Date.now() + validityDays * 86400000
            ),
            fingerprint: this.provider.fingerprint(material),
            material
        };

        this.keys.set(key.id, key);
        versions.push(key.id);
        this.aliases.set(alias, versions);

        this.audit.record(actor, "CREATE_KEY", key.id);

        return this.publicMetadata(key);
    }

    publicMetadata(key) {
        return {
            id: key.id,
            alias: key.alias,
            version: key.version,
            algorithm: key.algorithm,
            status: key.status,
            fingerprint: key.fingerprint,
            createdAt: key.createdAt.toISOString(),
            expiresAt: key.expiresAt.toISOString()
        };
    }

    requireKey(id) {
        const key = this.keys.get(id);

        if (!key || !key.material) {
            throw new ResourceNotFound(`Key not found: ${id}`);
        }

        return key;
    }

    rotate(actor, id) {
        this.authorization.authorize(actor, Permissions.ROTATE);

        const old = this.requireKey(id);

        if (old.status !== KeyStatus.ACTIVE) {
            throw new InvalidKeyState("Key is not active");
        }

        const replacement = this.createKey(
            actor,
            old.alias,
            {
                validityDays: Math.max(
                    1,
                    Math.ceil(
                        (old.expiresAt.getTime() - Date.now()) / 86400000
                    )
                )
            }
        );

        old.status = KeyStatus.DECRYPT_ONLY;

        this.audit.record(actor, "ROTATE_KEY", old.id);

        return replacement;
    }

    revoke(actor, id) {
        this.authorization.authorize(actor, Permissions.REVOKE);

        const key = this.requireKey(id);

        if (key.status === KeyStatus.DESTROYED) {
            throw new InvalidKeyState("Key already destroyed");
        }

        key.status = KeyStatus.REVOKED;
        this.audit.record(actor, "REVOKE_KEY", id);
    }

    destroy(actor, id) {
        this.authorization.authorize(actor, Permissions.ADMIN);

        const key = this.requireKey(id);

        if (![KeyStatus.REVOKED, KeyStatus.DECRYPT_ONLY].includes(
            key.status
        )) {
            throw new InvalidKeyState(
                "Key must be revoked or retired before destruction"
            );
        }

        // This removes the application's reference; it does not guarantee
        // physical memory erasure by the JavaScript runtime.
        key.material = null;
        key.status = KeyStatus.DESTROYED;

        this.audit.record(actor, "DESTROY_KEY", id);
    }

    getUsableKey(id, operation) {
        const key = this.requireKey(id);

        if (Date.now() >= key.expiresAt.getTime()) {
            throw new InvalidKeyState("Key has expired");
        }

        if (operation === "ENCRYPT" &&
            key.status !== KeyStatus.ACTIVE) {
            throw new InvalidKeyState("Key cannot encrypt");
        }

        if (operation === "DECRYPT" &&
            ![KeyStatus.ACTIVE, KeyStatus.DECRYPT_ONLY].includes(
                key.status
            )) {
            throw new InvalidKeyState("Key cannot decrypt");
        }

        return key;
    }

    encrypt(actor, id, plaintext, aad) {
        this.authorization.authorize(actor, Permissions.WRITE);

        const key = this.getUsableKey(id, "ENCRYPT");

        const envelope = this.provider.encrypt(
            key.material,
            Buffer.from(plaintext, "utf8"),
            aad
        );

        this.audit.record(actor, "ENCRYPT", id);

        return {
            keyId: id,
            keyVersion: key.version,
            aad,
            ...envelope
        };
    }

    decrypt(actor, envelope) {
        this.authorization.authorize(actor, Permissions.READ);

        const key = this.getUsableKey(
            envelope.keyId,
            "DECRYPT"
        );

        if (key.version !== envelope.keyVersion) {
            throw new SecurityError("Key version mismatch");
        }

        const plaintext = this.provider.decrypt(
            key.material,
            envelope,
            envelope.aad
        );

        this.audit.record(actor, "DECRYPT", key.id);

        return plaintext.toString("utf8");
    }

    inventory() {
        return [...this.keys.values()].map(
            key => this.publicMetadata(key)
        );
    }
}

// ============================================================
// ENVELOPE ENCRYPTION
// ============================================================

class EnvelopeEncryptionService {
    constructor(kms, provider) {
        this.kms = kms;
        this.provider = provider;
    }

    encrypt(actor, keyId, plaintext) {
        const dek = this.provider.generate();

        const dataEnvelope = this.provider.encrypt(
            dek,
            Buffer.from(plaintext, "utf8"),
            "application-data"
        );

        const wrappedDek = this.kms.encrypt(
            actor,
            keyId,
            dek.toString("base64"),
            "data-encryption-key"
        );

        return {
            dataEnvelope,
            wrappedDek
        };
    }

    decrypt(actor, packageData) {
        const dekBase64 = this.kms.decrypt(
            actor,
            packageData.wrappedDek
        );

        const dek = Buffer.from(dekBase64, "base64");

        return this.provider.decrypt(
            dek,
            packageData.dataEnvelope,
            "application-data"
        ).toString("utf8");
    }
}

// ============================================================
// SECRETS STORAGE
// ============================================================

class SecretVault {
    constructor(kms, authorization, audit) {
        this.kms = kms;
        this.authorization = authorization;
        this.audit = audit;
        this.records = new Map();
    }

    put(actor, name, value, keyId) {
        this.authorization.authorize(actor, Permissions.WRITE);

        if (!/^[a-zA-Z0-9/_-]{1,150}$/.test(name)) {
            throw new TypeError("Invalid secret name");
        }

        if (typeof value !== "string" || value.length === 0) {
            throw new TypeError("Secret value is required");
        }

        const previous = this.records.get(name);

        const encrypted = this.kms.encrypt(
            actor,
            keyId,
            value,
            `secret:${name}`
        );

        const record = {
            name,
            version: (previous?.version ?? 0) + 1,
            envelope: encrypted,
            updatedAt: new Date().toISOString(),
            enabled: true
        };

        this.records.set(name, record);
        this.audit.record(actor, "STORE_SECRET", name);

        return {
            name,
            version: record.version,
            updatedAt: record.updatedAt
        };
    }

    get(actor, name) {
        this.authorization.authorize(actor, Permissions.READ);

        const record = this.records.get(name);

        if (!record || !record.enabled) {
            throw new ResourceNotFound("Secret unavailable");
        }

        this.audit.record(actor, "READ_SECRET", name);

        return this.kms.decrypt(actor, record.envelope);
    }

    disable(actor, name) {
        this.authorization.authorize(actor, Permissions.ADMIN);

        const record = this.records.get(name);

        if (!record) {
            throw new ResourceNotFound("Secret not found");
        }

        record.enabled = false;
        record.envelope = null;

        this.audit.record(actor, "DISABLE_SECRET", name);
    }
}

// ============================================================
// CERTIFICATE INVENTORY
// ============================================================

class CertificateRegistry {
    constructor(audit) {
        this.certificates = new Map();
        this.audit = audit;
    }

    register(actor, data) {
        const required = [
            "commonName",
            "issuer",
            "serialNumber",
            "fingerprint",
            "notBefore",
            "notAfter"
        ];

        for (const field of required) {
            if (!data[field]) {
                throw new TypeError(`Missing ${field}`);
            }
        }

        if (!/^[a-f0-9]{64}$/i.test(data.fingerprint)) {
            throw new TypeError("Invalid SHA-256 fingerprint");
        }

        const start = new Date(data.notBefore);
        const end = new Date(data.notAfter);

        if (Number.isNaN(start.getTime()) ||
            Number.isNaN(end.getTime()) ||
            start >= end) {
            throw new TypeError("Invalid certificate validity");
        }

        if ([...this.certificates.values()].some(
            cert => cert.fingerprint === data.fingerprint
        )) {
            throw new SecurityError("Duplicate certificate");
        }

        const certificate = {
            id: crypto.randomUUID(),
            ...data,
            notBefore: start,
            notAfter: end,
            revoked: false
        };

        this.certificates.set(certificate.id, certificate);
        this.audit.record(actor, "REGISTER_CERTIFICATE", certificate.id);

        return this.metadata(certificate);
    }

    metadata(cert) {
        const now = new Date();

        let status = "VALID";

        if (cert.revoked) {
            status = "REVOKED";
        } else if (now >= cert.notAfter) {
            status = "EXPIRED";
        } else if (
            now >= new Date(cert.notAfter.getTime() - 30 * 86400000)
        ) {
            status = "EXPIRING";
        }

        return {
            id: cert.id,
            commonName: cert.commonName,
            issuer: cert.issuer,
            fingerprint: cert.fingerprint,
            notAfter: cert.notAfter.toISOString(),
            status
        };
    }

    revoke(actor, id) {
        const cert = this.certificates.get(id);

        if (!cert) {
            throw new ResourceNotFound("Certificate not found");
        }

        cert.revoked = true;
        this.audit.record(actor, "REVOKE_CERTIFICATE", id);
    }

    expiryReport() {
        return [...this.certificates.values()].map(
            cert => this.metadata(cert)
        );
    }
}

// ============================================================
// EXECUTABLE WORKFLOW
// ============================================================

async function main() {
    const audit = new AuditBus();

    audit.on("audit", event => {
        console.log(
            `[AUDIT] ${event.action} ${event.resource} ${event.outcome}`
        );
    });

    const auth = new AuthorizationService();

    auth.assign("security-admin", "security-admin");
    auth.assign("application", "application");
    auth.assign("compliance-auditor", "auditor");

    const provider = new LocalKeyProvider();

    const kms = new KeyManagementService(
        provider,
        auth,
        audit
    );

    const vault = new SecretVault(kms, auth, audit);

    const envelopeService = new EnvelopeEncryptionService(
        kms,
        provider
    );

    const certificates = new CertificateRegistry(audit);

    console.log("\n=== KEY MANAGEMENT ===");

    const key = kms.createKey(
        "security-admin",
        "payments/master-key"
    );

    console.log("Key:", key);

    // AES-GCM encryption and authenticated decryption.
    const encrypted = kms.encrypt(
        "application",
        key.id,
        "confidential-payment-record",
        "payment-record-1001"
    );

    console.log(
        "Decrypted:",
        kms.decrypt("application", encrypted)
    );

    // Authenticated encryption rejects modified ciphertext.
    const tampered = {
        ...encrypted,
        ciphertext: Buffer.from(
            "modified"
        ).toString("base64")
    };

    try {
        kms.decrypt("application", tampered);
    } catch (error) {
        console.log("Tampering rejected:", error.message);
    }

    // Envelope encryption separates data keys from master keys.
    const packageData = envelopeService.encrypt(
        "application",
        key.id,
        "large-sensitive-dataset"
    );

    console.log(
        "Envelope result:",
        envelopeService.decrypt("application", packageData)
    );

    // Store and rotate a database credential.
    console.log("\n=== SECRET VAULT ===");

    vault.put(
        "security-admin",
        "database/password",
        crypto.randomBytes(32).toString("base64url"),
        key.id
    );

    console.log(
        "Secret retrieved:",
        vault.get("application", "database/password").length,
        "characters"
    );

    vault.put(
        "security-admin",
        "database/password",
        crypto.randomBytes(40).toString("base64url"),
        key.id
    );

    console.log("Secret version:", vault.records.get(
        "database/password"
    ).version);

    // Rotate the master key while retaining old decryption capability.
    console.log("\n=== KEY ROTATION ===");

    const replacement = kms.rotate("security-admin", key.id);

    console.log("New key:", replacement);
    console.log(
        "Old key status:",
        kms.keys.get(key.id).status
    );

    console.log(
        "Historical ciphertext:",
        kms.decrypt("application", encrypted)
    );

    // New encryption uses the replacement key.
    const newEnvelope = kms.encrypt(
        "application",
        replacement.id,
        "new-generation-record",
        "record-2001"
    );

    console.log(
        "New encryption:",
        kms.decrypt("application", newEnvelope)
    );

    // Certificate metadata inventory.
    console.log("\n=== CERTIFICATE INVENTORY ===");

    certificates.register("security-admin", {
        commonName: "api.internal.example",
        issuer: "Internal Root CA",
        serialNumber: "CERT-1001",
        fingerprint: crypto
            .createHash("sha256")
            .update("certificate-der-data")
            .digest("hex"),
        notBefore: new Date(Date.now() - 86400000),
        notAfter: new Date(Date.now() + 120 * 86400000)
    });

    console.log(certificates.expiryReport());

    // Authorization failure.
    try {
        kms.rotate("application", replacement.id);
    } catch (error) {
        console.log("Expected denial:", error.message);
    }

    // Export audit metadata.
    await audit.export("security_audit.json");

    console.log("\nKey inventory:", kms.inventory());
    console.log("Audit events:", audit.events.length);

    // Verify important workflow properties.
    if (kms.keys.get(key.id).status !== KeyStatus.DECRYPT_ONLY) {
        throw new Error("Rotation invariant failed");
    }

    if (kms.decrypt("application", encrypted) !==
        "confidential-payment-record") {
        throw new Error("Historical decryption failed");
    }

    console.log("\nAll security workflow checks passed.");
}

main().catch(error => {
    console.error("Fatal workflow error:", error.message);
    process.exitCode = 1;
});
