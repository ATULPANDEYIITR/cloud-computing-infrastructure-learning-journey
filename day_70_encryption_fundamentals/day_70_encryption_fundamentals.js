"use strict";

/*
 * Encryption Fundamentals
 *
 * Node.js 20+
 *
 * Demonstrates:
 * 1. AES-256-GCM symmetric encryption.
 * 2. RSA-OAEP asymmetric encryption.
 * 3. Hybrid envelope encryption.
 * 4. Encryption at rest.
 * 5. TLS client configuration.
 * 6. Key rotation and lifecycle management.
 * 7. Digital signatures.
 * 8. Asynchronous file operations and integrity checks.
 *
 * Run:
 * node encryption_fundamentals.js
 */

const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");
const tls = require("node:tls");
const os = require("node:os");
const assert = require("node:assert/strict");

const ALGORITHM = "aes-256-gcm";
const KEY_LENGTH = 32;
const NONCE_LENGTH = 12;
const TAG_LENGTH = 16;

class EncryptionError extends Error {}
class AuthenticationError extends EncryptionError {}
class KeyManagementError extends EncryptionError {}

const KeyStatus = Object.freeze({
    ACTIVE: "ACTIVE",
    RETIRED: "RETIRED",
    REVOKED: "REVOKED"
});

function validateBuffer(value, field) {
    if (!Buffer.isBuffer(value)) {
        throw new TypeError(`${field} must be a Buffer`);
    }
}

function generateDataKey() {
    return crypto.randomBytes(KEY_LENGTH);
}

class AESGCMService {
    static encrypt(plaintext, key, associatedData = Buffer.alloc(0)) {
        validateBuffer(plaintext, "plaintext");
        validateBuffer(key, "key");
        validateBuffer(associatedData, "associatedData");

        if (key.length !== KEY_LENGTH) {
            throw new RangeError("AES-256 requires 32-byte keys");
        }

        const nonce = crypto.randomBytes(NONCE_LENGTH);

        const cipher = crypto.createCipheriv(
            ALGORITHM,
            key,
            nonce,
            { authTagLength: TAG_LENGTH }
        );

        cipher.setAAD(associatedData);

        const ciphertext = Buffer.concat([
            cipher.update(plaintext),
            cipher.final()
        ]);

        const tag = cipher.getAuthTag();

        return {
            algorithm: ALGORITHM,
            nonce: nonce.toString("base64"),
            ciphertext: ciphertext.toString("base64"),
            tag: tag.toString("base64")
        };
    }

    static decrypt(envelope, key, associatedData = Buffer.alloc(0)) {
        validateBuffer(key, "key");

        if (key.length !== KEY_LENGTH) {
            throw new RangeError("Invalid AES key length");
        }

        if (!envelope || envelope.algorithm !== ALGORITHM) {
            throw new EncryptionError("Unsupported envelope");
        }

        try {
            const nonce = Buffer.from(envelope.nonce, "base64");
            const ciphertext = Buffer.from(
                envelope.ciphertext,
                "base64"
            );
            const tag = Buffer.from(envelope.tag, "base64");

            if (
                nonce.length !== NONCE_LENGTH ||
                tag.length !== TAG_LENGTH
            ) {
                throw new EncryptionError("Invalid nonce or tag");
            }

            const decipher = crypto.createDecipheriv(
                ALGORITHM,
                key,
                nonce,
                { authTagLength: TAG_LENGTH }
            );

            decipher.setAAD(associatedData);
            decipher.setAuthTag(tag);

            return Buffer.concat([
                decipher.update(ciphertext),
                decipher.final()
            ]);

        } catch (error) {
            if (error instanceof EncryptionError) {
                throw error;
            }

            throw new AuthenticationError(
                "Authentication or decryption failed"
            );
        }
    }
}

class RSAService {
    constructor() {
        const pair = crypto.generateKeyPairSync("rsa", {
            modulusLength: 3072,
            publicExponent: 0x10001,
            publicKeyEncoding: {
                type: "spki",
                format: "pem"
            },
            privateKeyEncoding: {
                type: "pkcs8",
                format: "pem"
            }
        });

        this.publicKey = pair.publicKey;
        this.privateKey = pair.privateKey;
    }

    encrypt(plaintext) {
        validateBuffer(plaintext, "plaintext");

        return crypto.publicEncrypt(
            {
                key: this.publicKey,
                padding: crypto.constants.RSA_PKCS1_OAEP_PADDING,
                oaepHash: "sha256"
            },
            plaintext
        );
    }

    decrypt(ciphertext) {
        validateBuffer(ciphertext, "ciphertext");

        try {
            return crypto.privateDecrypt(
                {
                    key: this.privateKey,
                    padding: crypto.constants.RSA_PKCS1_OAEP_PADDING,
                    oaepHash: "sha256"
                },
                ciphertext
            );
        } catch {
            throw new AuthenticationError("RSA decryption failed");
        }
    }

    sign(message) {
        validateBuffer(message, "message");

        return crypto.sign("sha256", message, {
            key: this.privateKey,
            padding: crypto.constants.RSA_PKCS1_PSS_PADDING,
            saltLength: crypto.constants.RSA_PSS_SALTLEN_MAX_SIGN
        });
    }

    verify(message, signature) {
        return crypto.verify("sha256", message, {
            key: this.publicKey,
            padding: crypto.constants.RSA_PKCS1_PSS_PADDING,
            saltLength: crypto.constants.RSA_PSS_SALTLEN_MAX_SIGN
        }, signature);
    }
}

class HybridEncryption {
    static encrypt(plaintext, recipientPublicKey) {
        const dataKey = generateDataKey();

        const envelope = AESGCMService.encrypt(
            plaintext,
            dataKey,
            Buffer.from("hybrid-envelope-v1")
        );

        const wrappedKey = crypto.publicEncrypt(
            {
                key: recipientPublicKey,
                padding: crypto.constants.RSA_PKCS1_OAEP_PADDING,
                oaepHash: "sha256"
            },
            dataKey
        );

        return Object.freeze({
            version: 1,
            algorithm: "AES-256-GCM+RSA-OAEP-SHA256",
            wrappedKey: wrappedKey.toString("base64"),
            nonce: envelope.nonce,
            ciphertext: envelope.ciphertext,
            tag: envelope.tag
        });
    }

    static decrypt(envelope, privateKey) {
        if (
            !envelope ||
            envelope.version !== 1 ||
            envelope.algorithm !== "AES-256-GCM+RSA-OAEP-SHA256"
        ) {
            throw new EncryptionError("Unsupported envelope version");
        }

        try {
            const dataKey = crypto.privateDecrypt(
                {
                    key: privateKey,
                    padding: crypto.constants.RSA_PKCS1_OAEP_PADDING,
                    oaepHash: "sha256"
                },
                Buffer.from(envelope.wrappedKey, "base64")
            );

            return AESGCMService.decrypt(
                envelope,
                dataKey,
                Buffer.from("hybrid-envelope-v1")
            );

        } catch (error) {
            if (error instanceof EncryptionError) {
                throw error;
            }

            throw new AuthenticationError(
                "Hybrid envelope validation failed"
            );
        }
    }
}

class KeyVault {
    #keys = new Map();
    #activeKeyId = null;

    createKey() {
        const id = crypto.randomUUID();

        if (this.#activeKeyId) {
            this.#keys.get(this.#activeKeyId).status =
                KeyStatus.RETIRED;
        }

        this.#keys.set(id, {
            id,
            material: generateDataKey(),
            status: KeyStatus.ACTIVE,
            createdAt: new Date().toISOString()
        });

        this.#activeKeyId = id;

        return id;
    }

    getActiveKey() {
        if (!this.#activeKeyId) {
            throw new KeyManagementError("No active key");
        }

        return this.getKey(this.#activeKeyId);
    }

    getKey(id) {
        const key = this.#keys.get(id);

        if (!key || key.status === KeyStatus.REVOKED) {
            throw new KeyManagementError("Key unavailable");
        }

        return key;
    }

    rotate() {
        return this.createKey();
    }

    revoke(id) {
        const key = this.getKey(id);

        key.status = KeyStatus.REVOKED;

        if (this.#activeKeyId === id) {
            this.#activeKeyId = null;
        }
    }

    inventory() {
        return [...this.#keys.values()].map(key => ({
            id: key.id,
            status: key.status,
            createdAt: key.createdAt
        }));
    }
}

class EncryptedFileStore {
    constructor(vault) {
        this.vault = vault;
        this.aad = Buffer.from("secure-storage-v1");
    }

    async encrypt(source, destination) {
        const input = path.resolve(source);
        const output = path.resolve(destination);

        if (input === output) {
            throw new EncryptionError(
                "Input and output paths must differ"
            );
        }

        const plaintext = await fs.readFile(input);
        const key = this.vault.getActiveKey();

        const encrypted = AESGCMService.encrypt(
            plaintext,
            key.material,
            this.aad
        );

        const metadata = Buffer.from(JSON.stringify({
            version: 1,
            keyId: key.id,
            algorithm: ALGORITHM
        }));

        if (metadata.length > 65535) {
            throw new EncryptionError("Metadata too large");
        }

        const header = Buffer.alloc(6);
        header.write("ENC1", 0, "ascii");
        header.writeUInt16BE(metadata.length, 4);

        const outputData = Buffer.concat([
            header,
            metadata,
            Buffer.from(encrypted.nonce, "base64"),
            Buffer.from(encrypted.tag, "base64"),
            Buffer.from(encrypted.ciphertext, "base64")
        ]);

        const temporary = `${output}.${crypto.randomUUID()}.tmp`;

        try {
            const handle = await fs.open(temporary, "wx", 0o600);

            try {
                await handle.writeFile(outputData);
                await handle.sync();
            } finally {
                await handle.close();
            }

            await fs.rename(temporary, output);

        } catch (error) {
            await fs.rm(temporary, { force: true });
            throw error;
        }
    }

    async decrypt(source, destination) {
        const payload = await fs.readFile(source);

        if (
            payload.length < 6 + NONCE_LENGTH + TAG_LENGTH ||
            payload.subarray(0, 4).toString("ascii") !== "ENC1"
        ) {
            throw new EncryptionError("Invalid encrypted file");
        }

        const metadataLength = payload.readUInt16BE(4);
        const metadataEnd = 6 + metadataLength;

        if (
            payload.length <
            metadataEnd + NONCE_LENGTH + TAG_LENGTH
        ) {
            throw new EncryptionError("Truncated encrypted file");
        }

        let metadata;

        try {
            metadata = JSON.parse(
                payload.subarray(6, metadataEnd).toString("utf8")
            );
        } catch {
            throw new EncryptionError("Invalid metadata");
        }

        if (
            metadata.version !== 1 ||
            metadata.algorithm !== ALGORITHM
        ) {
            throw new EncryptionError("Unsupported file format");
        }

        const key = this.vault.getKey(metadata.keyId);

        const nonceStart = metadataEnd;
        const tagStart = nonceStart + NONCE_LENGTH;
        const ciphertextStart = tagStart + TAG_LENGTH;

        const encrypted = {
            algorithm: ALGORITHM,
            nonce: payload.subarray(
                nonceStart,
                tagStart
            ).toString("base64"),
            tag: payload.subarray(
                tagStart,
                ciphertextStart
            ).toString("base64"),
            ciphertext: payload.subarray(
                ciphertextStart
            ).toString("base64")
        };

        const plaintext = AESGCMService.decrypt(
            encrypted,
            key.material,
            this.aad
        );

        const output = path.resolve(destination);
        const temporary = `${output}.${crypto.randomUUID()}.tmp`;

        try {
            const handle = await fs.open(temporary, "wx", 0o600);

            try {
                await handle.writeFile(plaintext);
                await handle.sync();
            } finally {
                await handle.close();
            }

            await fs.rename(temporary, output);

        } catch (error) {
            await fs.rm(temporary, { force: true });
            throw error;
        }
    }
}

class TLSConfiguration {
    static createClientOptions() {
        return {
            minVersion: "TLSv1.2",
            rejectUnauthorized: true,
            checkServerIdentity: tls.checkServerIdentity
        };
    }
}

class EncryptionAudit {
    static fingerprint(data) {
        return crypto
            .createHash("sha256")
            .update(data)
            .digest("hex");
    }

    static compare(before, after) {
        return this.fingerprint(before) === this.fingerprint(after);
    }
}

async function runTests() {
    const key = generateDataKey();
    const message = Buffer.from(
        "Confidential enterprise transaction"
    );

    // AES-GCM round trip.
    const encrypted = AESGCMService.encrypt(message, key);

    assert.deepEqual(
        AESGCMService.decrypt(encrypted, key),
        message
    );

    // Authentication failure.
    const tampered = {
        ...encrypted,
        ciphertext: Buffer.from(
            Buffer.from(encrypted.ciphertext, "base64").map(
                (value, index) => index === 0 ? value ^ 1 : value
            )
        ).toString("base64")
    };

    assert.throws(
        () => AESGCMService.decrypt(tampered, key),
        AuthenticationError
    );

    // RSA and digital signature.
    const rsa = new RSAService();

    assert.deepEqual(
        rsa.decrypt(rsa.encrypt(message)),
        message
    );

    const signature = rsa.sign(message);

    assert.equal(rsa.verify(message, signature), true);
    assert.equal(
        rsa.verify(Buffer.from("modified"), signature),
        false
    );

    // Hybrid encryption.
    const hybrid = HybridEncryption.encrypt(
        message,
        rsa.publicKey
    );

    assert.deepEqual(
        HybridEncryption.decrypt(hybrid, rsa.privateKey),
        message
    );

    // Key rotation.
    const vault = new KeyVault();

    const firstKey = vault.createKey();
    const secondKey = vault.rotate();

    assert.notEqual(firstKey, secondKey);
    assert.equal(vault.getKey(firstKey).status, KeyStatus.RETIRED);

    // Encrypted file workflow.
    const directory = await fs.mkdtemp(
        path.join(os.tmpdir(), "encryption-demo-")
    );

    try {
        const source = path.join(directory, "input.txt");
        const encryptedFile = path.join(directory, "input.enc");
        const restored = path.join(directory, "restored.txt");

        await fs.writeFile(source, message, { mode: 0o600 });

        const store = new EncryptedFileStore(vault);

        await store.encrypt(source, encryptedFile);
        await store.decrypt(encryptedFile, restored);

        const restoredData = await fs.readFile(restored);

        assert.deepEqual(restoredData, message);

        console.log("File encryption and recovery: PASS");

    } finally {
        await fs.rm(directory, {
            recursive: true,
            force: true
        });
    }

    assert.equal(EncryptionAudit.compare(message, message), true);

    console.log("AES-256-GCM: PASS");
    console.log("Tampering detection: PASS");
    console.log("RSA-OAEP: PASS");
    console.log("RSA-PSS signatures: PASS");
    console.log("Hybrid encryption: PASS");
    console.log("Key rotation: PASS");
    console.log("Content fingerprinting: PASS");

    console.log("\nTLS client configuration:");
    console.log(TLSConfiguration.createClientOptions());

    console.log("\nKey inventory:");
    console.log(vault.inventory());
}

async function main() {
    try {
        await runTests();
    } catch (error) {
        console.error("Execution failed:", error.message);
        process.exitCode = 1;
    }
}

main();
